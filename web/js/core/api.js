/**
 * Network boundary.
 *
 * The frontend never talks to the attestation API and never sees a token:
 * it asks this backend, which holds the credentials.
 *
 * Nothing here is hardcoded. Every value the viewer shows comes from
 * GET /api/records/{code}, which the backend builds from the sheet in
 * custody and its attestation. In a product whose whole claim is
 * authenticity, a placeholder that looks like a hash is worse than an empty
 * field: someone copies it into a block explorer, finds nothing, and the
 * next question is not about the placeholder.
 *
 * WHERE EACH FIELD COMES FROM in GET /stamp/get/?byTrxid=…
 * The obvious-looking fields are not the right ones. `integrity.tx_lacchain`
 * holds "0x" and `integrity.infocid` is empty even on a fully anchored
 * record; the real anchors live under `networks` and `block`.
 *
 *   evidence      result.integrity.evidence
 *   subject       result.integrity.subject
 *   process code  result.integrity.transactionType
 *   results       result.integrity.info            (base64 JSON)
 *   identity      result.integrity.data            (base64 JSON)
 *   coordinates   result.ownership.lat / .long
 *   IPFS          result.block.ipfs                NOT integrity.infocid
 *   LACChain      result.networks.mainnet.lacchain NOT integrity.tx_lacchain
 *   Rollux        result.networks.mainnet.rollux   NOT integrity.tx_rollux
 *   merkle root   result.block.hashblock
 *   block number  result.block.number
 *   sealed        result.existence.timestamp       (epoch ms)
 *   anchored      result.existence.anchored
 *   anchor state  result.blockchains.recipient     ("anchored" when complete)
 */

export class RecordUnavailable extends Error {}

export async function fetchRecord(code) {
  const response = await fetch(`api/records/${encodeURIComponent(code)}`, {
    headers: { Accept: 'application/json' },
    credentials: 'omit'
  });
  if (response.status === 404) throw new RecordUnavailable('not found');
  if (!response.ok) throw new Error(`api ${response.status}`);
  return response.json();
}

export function currentCode() {
  const path = location.pathname.replace(/\/+$/, '').split('/').pop();
  return /^[A-Za-z0-9_-]{6,120}$/.test(path) ? path : '';
}
