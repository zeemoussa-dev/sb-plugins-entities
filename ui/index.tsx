import type { PluginUi } from '../../pluginHost/types';
import { EntitiesPage } from './EntitiesPage';

const ui: PluginUi = {
  settingsPages: [{ path: '', label: 'Entities', component: EntitiesPage }],
  // Filled by this plugin's subject enricher from the Thread's customer/<slug> tag.
  cockpitInfoFields: [{ subjectKind: 'email', label: 'Customer', key: 'customer' }],
};

export default ui;
