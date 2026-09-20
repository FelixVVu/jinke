import { selectCompanyOffices } from './model.js';

export const COMPANY_SOURCE = 'company-access-offices';
export const COMPANY_LAYER = 'company-access-circles';

/** Lives for the lifetime of the Map, not its disposable style. */
export class CompanyAccessLayers {
  constructor(map, onSelect = () => {}) {
    this.map = map;
    this.output = null;
    this.limit = 50;
    this.visible = false;
    this.onSelect = onSelect;
    this.bound = false;
    this.handlers = {
      mouseenter: () => { map.getCanvas().style.cursor = 'pointer'; },
      mouseleave: () => { map.getCanvas().style.cursor = ''; },
      click: event => {
        const id = event.features?.[0]?.id;
        const office = this.output?.offices.features.find(f => f.id === id);
        if (office && office.properties.reach_minutes.includes(this.limit === 'all' ? 50 : this.limit)) this.onSelect(office.properties);
      },
    };
  }

  setState({ output = this.output, limit = this.limit, visible = this.visible } = {}) {
    // Check the limit before mutating state. Data must be validated at ingestion.
    selectCompanyOffices(output, limit);
    this.output = output;
    this.limit = limit;
    this.visible = Boolean(visible && output?.metadata.status === 'ready');
    this.restore();
  }

  restore() {
    const map = this.map;
    // Existing coordinator restores station layers first; no competing style listener.
    if (!map.getStyle() || !map.getLayer('station-circle')) return false;
    const data = selectCompanyOffices(this.output, this.limit);
    if (!map.getSource(COMPANY_SOURCE)) map.addSource(COMPANY_SOURCE, { type: 'geojson', data });
    else map.getSource(COMPANY_SOURCE).setData(data);
    if (!map.getLayer(COMPANY_LAYER)) map.addLayer({
      id: COMPANY_LAYER, type: 'circle', source: COMPANY_SOURCE,
      paint: { 'circle-color': '#b35f24', 'circle-radius': 5,
        'circle-stroke-color': '#fff', 'circle-stroke-width': 1.5 },
    }, 'station-circle');
    map.setLayoutProperty(COMPANY_LAYER, 'visibility', this.visible ? 'visible' : 'none');
    if (!this.bound) {
      for (const [event, handler] of Object.entries(this.handlers)) map.on(event, COMPANY_LAYER, handler);
      this.bound = true;
    }
    return true;
  }

  destroy() {
    if (this.bound) for (const [event, handler] of Object.entries(this.handlers)) this.map.off(event, COMPANY_LAYER, handler);
    this.bound = false;
    this.map.getCanvas().style.cursor = '';
    if (this.map.getLayer(COMPANY_LAYER)) this.map.removeLayer(COMPANY_LAYER);
    if (this.map.getSource(COMPANY_SOURCE)) this.map.removeSource(COMPANY_SOURCE);
  }
}
