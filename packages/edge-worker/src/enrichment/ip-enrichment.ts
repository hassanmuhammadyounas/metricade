export type IpMeta = {
  ip: string;
  ip_type: 'residential' | 'datacenter' | 'vpn' | 'tor' | 'unknown';
  ip_country: string;
  ip_asn: string;
};

export async function enrichIp(ip: string): Promise<IpMeta> {
  // Cloudflare provides geo data via request cf object — no external API call needed
  // The cf object is available on the Request in the Worker context
  // This is a placeholder — wire in c.req.raw.cf in the ingest route for production
  return {
    ip,
    ip_type: 'unknown',
    ip_country: 'unknown',
    ip_asn: 'unknown',
  };
}
