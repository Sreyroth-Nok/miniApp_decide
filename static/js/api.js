import { devChat, devUser, inTelegram, initData } from './tg.js';

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(method, path, payload) {
  const headers = { 'Content-Type': 'application/json' };
  if (inTelegram) {
    headers.Authorization = `tma ${initData()}`;
  } else {
    headers['X-Dev-User'] = devUser();
    if (devChat()) headers['X-Dev-Chat'] = devChat();
  }

  let response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      body: payload === undefined ? undefined : JSON.stringify(payload),
    });
  } catch {
    throw new ApiError('No connection. Check your internet and try again.', 0);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(data.error || 'The server had a problem. Try again.', response.status);
  return data;
}

export const api = {
  config: () => request('GET', '/config'),
  recent: () => request('GET', '/recent'),
  poll: (id) => request('GET', `/polls/${id}`),
  create: (data) => request('POST', '/polls', data),
  vote: (id, choices) => request('POST', `/polls/${id}/vote`, { choices }),
  addOption: (id, label) => request('POST', `/polls/${id}/options`, { label }),
  spin: (id, data) => request('POST', `/polls/${id}/spin`, data),
  close: (id) => request('POST', `/polls/${id}/close`, {}),
  decide: (id, optionId) => request('POST', `/polls/${id}/decide`, { option_id: optionId }),
  reopen: (id) => request('POST', `/polls/${id}/reopen`, {}),
  prepared: (id) => request('POST', `/polls/${id}/prepared-message`, {}),
};
