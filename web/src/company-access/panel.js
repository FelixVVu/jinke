import { COMPANY_DISCLOSURE } from './schema.js';

export const companyPanelMarkup = `
  <details id="companyAccess" class="control-section company-access">
    <summary>Company Access</summary>
    <div class="details-content">
      <p id="companyAccessStatus" role="status" aria-live="polite"></p>
      <label class="toggle"><input id="showCompanyOffices" type="checkbox" disabled> Show company offices</label>
      <p class="company-access-note">${COMPANY_DISCLOSURE}</p>
      <p id="companyAccessSelection" hidden></p>
    </div>
  </details>`;

export function companyPanelState(output, limit) {
  const minutes = limit === 'all' ? 50 : limit;
  if (!output || output.metadata.status !== 'ready') return {
    enabled: false, message: 'Company-office data has not been connected yet.',
  };
  const record = output.summary.records.find(r => r.limit_minutes === minutes);
  return { enabled: true, message: `${record.office_count} sourced offices · ${record.hub_count} hubs · within ${minutes} minutes${limit === 'all' ? ' (All reach view)' : ''}.` };
}

export function renderCompanyPanel(root, output, limit) {
  const view = companyPanelState(output, limit);
  root.querySelector('#companyAccessStatus').textContent = view.message;
  const toggle = root.querySelector('#showCompanyOffices');
  toggle.disabled = !view.enabled;
  if (!view.enabled) toggle.checked = false;
  const selection = root.querySelector('#companyAccessSelection');
  selection.hidden = true;
  selection.textContent = '';
}
