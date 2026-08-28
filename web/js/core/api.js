/**
 * Network boundary.
 *
 * The frontend never talks to Stamping and never sees an API token: it asks
 * this backend, which holds the credentials. While the HTTP layer is being
 * built, FIXTURE stands in for the response, shaped exactly like the real
 * contract so swapping in fetch() changes nothing above this file.
 */

const FIXTURE = {
  status: 'verified',
  station: '035253',
  process: { code: 'EMC-2026', name: 'Elecciones Municipales 2026' },
  document: {
    pages: ['assets/sample/page-1.webp'],
    pdf_url: 'assets/sample/valid.pdf',
    size: '8.8 KB',
    page_count: 1
  },
  attestation: {
    evidence: '33abfeafad34c92bb81577d360e94dc16c8f23f0cf2d035dd9d1480adff6b40e',
    trx_id: '9e6f935c4a734ca07609269d43b7c70e6af22638',
    sealed_at: '2026-08-28 21:34:02 UTC',
    anchored_at: '2026-08-28 21:36:18 UTC',
    block_number: '1 482 907',
    anchors: [
      { key: 'IPFS', label_key: 'anchors.ipfs', network: 'InterPlanetary File System',
        value: 'bafybeigd7rkzmqf4xn2vhy6cw3plu5ktjs8oa9dnr2xewb4mfq7ch1yvzk',
        url: 'https://ipfs.io/ipfs/bafybeigd7rkzmqf4xn2vhy6cw3plu5ktjs8oa9dnr2xewb4mfq7ch1yvzk',
        logo: 'assets/networks/ipfs.svg' },
      { key: 'LNET', label_key: 'anchors.lnet', network: 'LACChain · chainId 648541',
        value: '0x7f3ac9d2e814b06592cd7a1e4f80b3652ade9c17d40f8b2e6539ac81fd0742b9',
        url: 'https://explorer.lacnet.com/tx/0x7f3ac9d2e814b06592cd7a1e4f80b3652ade9c17d40f8b2e6539ac81fd0742b9',
        logo: 'https://stamping.io/admin/img/lacchain-grid.png' },
      { key: 'RLX', label_key: 'anchors.rollux', network: 'Rollux · chainId 570',
        value: '0x2e91cb45a70df836195c2ad8be403f7169dc582a4e0b91735fc6de2408ab7159',
        url: 'https://explorer.rollux.com/tx/0x2e91cb45a70df836195c2ad8be403f7169dc582a4e0b91735fc6de2408ab7159',
        logo: 'https://stamping.io/admin/img/1087373765014454322_kg0Q8IQiPB8b.png' },
      { key: 'STP', label_key: 'anchors.stamping', network: 'Stamping.io · Merkle tree',
        value: 'c4a71e93f0b285d61a4e7c8b3f902da5e618b7c04df29a3e5187b60c2fa4e9d1',
        url: 'https://stamping.io/es/view/?9e6f935c4a734ca07609269d43b7c70e6af22638',
        logo: 'https://stamping.io/img/favicon.ico',
        action_key: 'verify.view_merkle', is_root: true }
    ]
  },
  signature: {
    valid: true, profile: 'PAdES-LTA', coverage: 100, revision: '1 de 1',
    signers: [
      { name: 'ONPE — Oficina Nacional de Procesos Electorales',
        id: 'RUC 20XXXXXXXXX', role: 'Digitalización y custodia del acta',
        authority: 'UANATACA S.A.',
        authority_kind: 'Prestador cualificado de servicios de confianza',
        signed_at: '2026-08-28 21:30:11 UTC',
        badges: ['Sello de tiempo cualificado', 'Validable a largo plazo', 'Certificado vigente'] }
    ]
  },
  location: {
    venue: 'I.E. 1120 Pedro A. Labarthe', district: 'San Miguel',
    province: 'Lima', ubigeo: '150132', latitude: -12.0768, longitude: -77.0916
  },
  results: {
    eligible_voters: 287, voters: 241, valid_votes: 223, null_votes: 7, blank_votes: 11,
    options: [
      { name: 'Movimiento Regional Unidad', party: 'M.R.U. + Alianza', votes: 86 },
      { name: 'Alianza Cívica del Litoral', party: 'ACL', votes: 62 },
      { name: 'Frente Vecinal Independiente', party: 'Frente Vecinal', votes: 44 },
      { name: 'Partido del Progreso Local', party: 'P.P.L.', votes: 31 }
    ]
  }
};

export async function fetchRecord(code) {
  // TODO: replace with `await fetch(\`api/records/${code}\`)` once the
  // FastAPI layer is serving. The shape does not change.
  await new Promise(resolve => setTimeout(resolve, 120));
  return FIXTURE;
}

export function currentCode() {
  const path = location.pathname.replace(/\/+$/, '').split('/').pop();
  return /^[A-Za-z0-9_-]{6,64}$/.test(path) ? path : 'preview';
}
