-- Add extended_communities field to route_updates table
-- Extended communities are used in EVPN for route targets, OSPF domain IDs, etc.

ALTER TABLE route_updates
ADD COLUMN IF NOT EXISTS extended_communities TEXT[];

-- Add index for extended communities searches
CREATE INDEX IF NOT EXISTS idx_route_extended_communities
ON route_updates USING GIN (extended_communities)
WHERE extended_communities IS NOT NULL;
