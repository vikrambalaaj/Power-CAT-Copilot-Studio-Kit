import { loadCustomer } from './service.js';

export function customerSummary(id) {
  const customer = loadCustomer(id);
  return `${customer.id}:${customer.status}`;
}
