-- Add route state tracking table
-- Tracks current state and lifetime statistics for each unique route

-- Route state table: maintains current state of each unique route
-- This complements the time-series route_updates table with fast state lookups
CREATE TABLE IF NOT EXISTS route_state (
    -- Route identifier (composite key)
    bmp_peer_ip INET NOT NULL,
    bgp_peer_ip INET NOT NULL,
    family TEXT NOT NULL,
    prefix CIDR,  -- Nullable for EVPN routes without IP prefix

    -- Timestamps
    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    last_state_change TIMESTAMPTZ NOT NULL,

    -- Current state
    is_withdrawn BOOLEAN NOT NULL DEFAULT FALSE,

    -- Statistics
    learn_count INTEGER NOT NULL DEFAULT 1,  -- Number of times route was learned (advertised)
    withdraw_count INTEGER NOT NULL DEFAULT 0,  -- Number of times route was withdrawn

    -- Latest route attributes (for convenience)
    next_hop INET,
    as_path INTEGER[],
    communities TEXT[],
    extended_communities TEXT[],
    med INTEGER,
    local_pref INTEGER,

    -- EVPN-specific fields
    evpn_route_type INTEGER,
    evpn_rd TEXT,
    evpn_esi TEXT,
    mac_address TEXT
);

-- Unique constraints for different route families
-- For IP routes (ipv4_unicast, ipv6_unicast): prefix is the unique identifier
CREATE UNIQUE INDEX IF NOT EXISTS idx_route_state_ip_routes
ON route_state (bmp_peer_ip, bgp_peer_ip, family, prefix)
WHERE family IN ('ipv4_unicast', 'ipv6_unicast') AND prefix IS NOT NULL;

-- For EVPN routes: combination of EVPN-specific fields provides uniqueness
-- EVPN route uniqueness depends on route type, RD, and other fields
CREATE UNIQUE INDEX IF NOT EXISTS idx_route_state_evpn_routes
ON route_state (bmp_peer_ip, bgp_peer_ip, family,
                COALESCE(evpn_rd, ''),
                COALESCE(evpn_esi, ''),
                COALESCE(mac_address, ''),
                COALESCE(prefix::TEXT, ''))
WHERE family = 'evpn';

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_route_state_first_seen ON route_state (first_seen DESC);
CREATE INDEX IF NOT EXISTS idx_route_state_last_seen ON route_state (last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_route_state_withdrawn ON route_state (is_withdrawn) WHERE is_withdrawn = TRUE;
CREATE INDEX IF NOT EXISTS idx_route_state_family ON route_state (family);
CREATE INDEX IF NOT EXISTS idx_route_state_prefix ON route_state (prefix);
CREATE INDEX IF NOT EXISTS idx_route_state_bmp_peer ON route_state (bmp_peer_ip);

-- Index for high-churn routes (learned/withdrawn frequently)
CREATE INDEX IF NOT EXISTS idx_route_state_churn ON route_state ((learn_count + withdraw_count) DESC)
WHERE learn_count + withdraw_count > 10;

-- Function to update route state on new route update
-- This is called by the application after inserting into route_updates
CREATE OR REPLACE FUNCTION update_route_state(
    p_time TIMESTAMPTZ,
    p_bmp_peer_ip INET,
    p_bgp_peer_ip INET,
    p_family TEXT,
    p_prefix CIDR,
    p_next_hop INET,
    p_as_path INTEGER[],
    p_communities TEXT[],
    p_extended_communities TEXT[],
    p_med INTEGER,
    p_local_pref INTEGER,
    p_is_withdrawn BOOLEAN,
    p_evpn_route_type INTEGER,
    p_evpn_rd TEXT,
    p_evpn_esi TEXT,
    p_mac_address TEXT
) RETURNS VOID AS $$
DECLARE
    v_current_withdrawn BOOLEAN;
    v_state_changed BOOLEAN := FALSE;
    v_row_count INTEGER;
BEGIN
    -- Check if route exists and get current withdrawn state
    -- For IP routes, match on prefix; for EVPN, match on EVPN fields
    IF p_family IN ('ipv4_unicast', 'ipv6_unicast') THEN
        SELECT is_withdrawn INTO v_current_withdrawn
        FROM route_state
        WHERE bmp_peer_ip = p_bmp_peer_ip
          AND bgp_peer_ip = p_bgp_peer_ip
          AND family = p_family
          AND prefix = p_prefix;
    ELSIF p_family = 'evpn' THEN
        SELECT is_withdrawn INTO v_current_withdrawn
        FROM route_state
        WHERE bmp_peer_ip = p_bmp_peer_ip
          AND bgp_peer_ip = p_bgp_peer_ip
          AND family = p_family
          AND COALESCE(evpn_rd, '') = COALESCE(p_evpn_rd, '')
          AND COALESCE(evpn_esi, '') = COALESCE(p_evpn_esi, '')
          AND COALESCE(mac_address, '') = COALESCE(p_mac_address, '')
          AND COALESCE(prefix::TEXT, '') = COALESCE(p_prefix::TEXT, '');
    END IF;

    -- Determine if state changed
    IF FOUND THEN
        v_state_changed := (v_current_withdrawn != p_is_withdrawn);

        -- Update existing route
        IF p_family IN ('ipv4_unicast', 'ipv6_unicast') THEN
            UPDATE route_state SET
                last_seen = p_time,
                last_state_change = CASE WHEN v_state_changed THEN p_time ELSE last_state_change END,
                is_withdrawn = p_is_withdrawn,
                learn_count = learn_count + CASE WHEN v_state_changed AND NOT p_is_withdrawn THEN 1 ELSE 0 END,
                withdraw_count = withdraw_count + CASE WHEN v_state_changed AND p_is_withdrawn THEN 1 ELSE 0 END,
                next_hop = CASE WHEN NOT p_is_withdrawn THEN p_next_hop ELSE next_hop END,
                as_path = CASE WHEN NOT p_is_withdrawn THEN p_as_path ELSE as_path END,
                communities = CASE WHEN NOT p_is_withdrawn THEN p_communities ELSE communities END,
                extended_communities = CASE WHEN NOT p_is_withdrawn THEN p_extended_communities ELSE extended_communities END,
                med = CASE WHEN NOT p_is_withdrawn THEN p_med ELSE med END,
                local_pref = CASE WHEN NOT p_is_withdrawn THEN p_local_pref ELSE local_pref END
            WHERE bmp_peer_ip = p_bmp_peer_ip
              AND bgp_peer_ip = p_bgp_peer_ip
              AND family = p_family
              AND prefix = p_prefix;
        ELSIF p_family = 'evpn' THEN
            UPDATE route_state SET
                last_seen = p_time,
                last_state_change = CASE WHEN v_state_changed THEN p_time ELSE last_state_change END,
                is_withdrawn = p_is_withdrawn,
                learn_count = learn_count + CASE WHEN v_state_changed AND NOT p_is_withdrawn THEN 1 ELSE 0 END,
                withdraw_count = withdraw_count + CASE WHEN v_state_changed AND p_is_withdrawn THEN 1 ELSE 0 END,
                next_hop = CASE WHEN NOT p_is_withdrawn THEN p_next_hop ELSE next_hop END,
                as_path = CASE WHEN NOT p_is_withdrawn THEN p_as_path ELSE as_path END,
                communities = CASE WHEN NOT p_is_withdrawn THEN p_communities ELSE communities END,
                extended_communities = CASE WHEN NOT p_is_withdrawn THEN p_extended_communities ELSE extended_communities END,
                med = CASE WHEN NOT p_is_withdrawn THEN p_med ELSE med END,
                local_pref = CASE WHEN NOT p_is_withdrawn THEN p_local_pref ELSE local_pref END,
                evpn_route_type = CASE WHEN NOT p_is_withdrawn THEN p_evpn_route_type ELSE evpn_route_type END,
                evpn_rd = CASE WHEN NOT p_is_withdrawn THEN p_evpn_rd ELSE evpn_rd END,
                evpn_esi = CASE WHEN NOT p_is_withdrawn THEN p_evpn_esi ELSE evpn_esi END,
                mac_address = CASE WHEN NOT p_is_withdrawn THEN p_mac_address ELSE mac_address END
            WHERE bmp_peer_ip = p_bmp_peer_ip
              AND bgp_peer_ip = p_bgp_peer_ip
              AND family = p_family
              AND COALESCE(evpn_rd, '') = COALESCE(p_evpn_rd, '')
              AND COALESCE(evpn_esi, '') = COALESCE(p_evpn_esi, '')
              AND COALESCE(mac_address, '') = COALESCE(p_mac_address, '')
              AND COALESCE(prefix::TEXT, '') = COALESCE(p_prefix::TEXT, '');
        END IF;
    ELSE
        -- Insert new route
        INSERT INTO route_state (
            bmp_peer_ip,
            bgp_peer_ip,
            family,
            prefix,
            first_seen,
            last_seen,
            last_state_change,
            is_withdrawn,
            learn_count,
            withdraw_count,
            next_hop,
            as_path,
            communities,
            extended_communities,
            med,
            local_pref,
            evpn_route_type,
            evpn_rd,
            evpn_esi,
            mac_address
        ) VALUES (
            p_bmp_peer_ip,
            p_bgp_peer_ip,
            p_family,
            p_prefix,
            p_time,
            p_time,
            p_time,
            p_is_withdrawn,
            CASE WHEN p_is_withdrawn THEN 0 ELSE 1 END,
            CASE WHEN p_is_withdrawn THEN 1 ELSE 0 END,
            p_next_hop,
            p_as_path,
            p_communities,
            p_extended_communities,
            p_med,
            p_local_pref,
            p_evpn_route_type,
            p_evpn_rd,
            p_evpn_esi,
            p_mac_address
        );
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Example queries for common use cases:

-- Find routes that have been relearned (learn_count > 1)
-- SELECT prefix, learn_count, withdraw_count, first_seen, last_seen, last_state_change
-- FROM route_state
-- WHERE learn_count > 1
-- ORDER BY learn_count DESC
-- LIMIT 100;

-- Find high-churn routes (frequent flapping)
-- SELECT prefix, learn_count, withdraw_count,
--        (learn_count + withdraw_count) as total_changes,
--        last_state_change
-- FROM route_state
-- WHERE learn_count + withdraw_count > 10
-- ORDER BY total_changes DESC;

-- Find routes first seen in the last hour
-- SELECT prefix, first_seen, is_withdrawn
-- FROM route_state
-- WHERE first_seen > NOW() - INTERVAL '1 hour'
-- ORDER BY first_seen DESC;

-- Find currently withdrawn routes
-- SELECT prefix, bgp_peer_ip, first_seen, last_seen, last_state_change, withdraw_count
-- FROM route_state
-- WHERE is_withdrawn = TRUE
-- ORDER BY last_state_change DESC;
