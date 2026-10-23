// AMap returns pipe-separated categories. Discovery eligibility is not an
// assertion that the point is an office or that the company is in Core+.
export const providerTypes=value=>String(value||'').split('|').map(s=>s.trim()).filter(s=>/^\d{6}$/.test(s));
export const corporateType=value=>providerTypes(value).some(t=>t.startsWith('17')||t==='141100');
export const companyType=value=>providerTypes(value).some(t=>t.startsWith('1702'));
export const mixedCommercialType=value=>providerTypes(value).some(t=>/^(05|06|07|08|12|13)/.test(t));
