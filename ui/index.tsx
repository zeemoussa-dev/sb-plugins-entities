import type { PluginUi } from '../../pluginHost/types';
import { AccountPage } from './AccountPage';
import { AccountsPage } from './AccountsPage';
import { EntitiesPage } from './EntitiesPage';
import './accounts.css';

const ui: PluginUi = {
  routes: [
    { path: '/entities', component: AccountsPage },
    { path: '/entities/:kind/:stem', component: AccountPage },
  ],
  nav: [{ to: '/entities', label: 'Customers & Partners', icon: '🏢' }],
  settingsPages: [{ path: '', label: 'Entities', component: EntitiesPage }],
  // Filled by this plugin's subject enricher from the Thread's customer/<slug> tag.
  cockpitInfoFields: [{ subjectKind: 'email', label: 'Customer', key: 'customer' }],
};

export default ui;
