import { setupWorker } from 'msw/browser';

import { handlers, operationsHandlers } from './handlers';

export const worker = setupWorker(...handlers);
export const backendPlaceholderWorker = setupWorker(...operationsHandlers);
