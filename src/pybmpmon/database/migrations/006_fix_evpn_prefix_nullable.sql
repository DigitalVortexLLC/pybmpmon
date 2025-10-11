-- Fix route_state table to support EVPN routes without IP prefix
-- This migration makes the prefix column nullable and updates unique constraints

-- Drop the old primary key (if it exists)
ALTER TABLE route_state DROP CONSTRAINT IF EXISTS route_state_pkey;

-- Make prefix nullable
ALTER TABLE route_state ALTER COLUMN prefix DROP NOT NULL;

-- Create unique constraints for different route families
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
