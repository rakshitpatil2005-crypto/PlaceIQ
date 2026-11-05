import assert from 'node:assert/strict';
import test from 'node:test';
import { getAuthenticationErrorMessage } from './authError.js';

test('normalizes authentication and FastAPI validation errors to safe text', () => {
  assert.equal(
    getAuthenticationErrorMessage({
      response: { data: { detail: 'Invalid email or password' } },
    }),
    'Invalid email or password',
  );
  assert.equal(
    getAuthenticationErrorMessage({
      response: {
        data: {
          detail: [
            { loc: ['body', 'email'], msg: 'Enter a valid email address.' },
            { loc: ['body', 'password'], msg: 'Field required.' },
          ],
        },
      },
    }),
    'Enter a valid email address. Field required.',
  );
  assert.equal(getAuthenticationErrorMessage({}), 'Authentication failed');
});
