export type IpMeta = {
  ip: string;
  ip_country: string;
  ip_asn: string;
  ip_org: string;
  ip_type: 'residential' | 'datacenter' | 'unknown';
  ip_timezone: string;
};

// Known datacenter/cloud ASNs — residential if not in this list
const DATACENTER_ASNS = new Set([
  16509, 14618,  // AWS
  15169,          // Google Cloud
  8075, 3598,    // Microsoft Azure
  14061,          // DigitalOcean
  63949,          // Linode / Akamai
  24940,          // Hetzner
  16276,          // OVH
  20473,          // Vultr
  13335,          // Cloudflare
  54113,          // Fastly
  60781,          // LeaseWeb
  36351,          // SoftLayer / IBM
  46664,          // Contabo
  212238,         // Datacamp / Serverius
]);

type CfGeo = {
  country?: string;
  asn?: number;
  asOrganization?: string;
  timezone?: string;
};

export function enrichIp(ip: string, cf?: CfGeo): IpMeta {
  const country = cf?.country ?? 'unknown';
  const asn = cf?.asn ? String(cf.asn) : 'unknown';
  const org = cf?.asOrganization ?? 'unknown';
  const ipType = cf?.asn
    ? (DATACENTER_ASNS.has(cf.asn) ? 'datacenter' : 'residential')
    : 'unknown';

  return { ip, ip_country: country, ip_asn: asn, ip_org: org, ip_type: ipType, ip_timezone: cf?.timezone ?? 'unknown' };
}
