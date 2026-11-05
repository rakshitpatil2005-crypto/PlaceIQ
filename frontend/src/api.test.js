import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { createServer } from 'vite';

test('uses the current development host and leaves login 401 errors visible', async () => {
  const previousWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');
  const previousStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  let removedToken = false;
  let destination = '';

  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      location: {
        protocol: 'http:',
        hostname: 'placeiq-device.test',
        set href(value) {
          destination = value;
        },
      },
    },
  });
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: () => 'test-token',
      removeItem: () => {
        removedToken = true;
      },
    },
  });

  const vite = await createServer({
    configFile: fileURLToPath(new URL('../vite.config.js', import.meta.url)),
    server: { middlewareMode: true },
    appType: 'custom',
  });

  try {
    const { default: api } = await vite.ssrLoadModule('/src/api.js');
    assert.equal(api.defaults.baseURL, 'http://placeiq-device.test:8000');

    const loginError = Object.assign(new Error('Unauthorized'), {
      response: { status: 401, data: { detail: 'Invalid email or password' } },
    });
    await assert.rejects(
      api.post('/auth/login', {}, {
        adapter: async (config) => {
          loginError.config = config;
          throw loginError;
        },
      }),
      (error) => error === loginError,
    );
    assert.equal(removedToken, false);
    assert.equal(destination, '');

    const protectedError = Object.assign(new Error('Unauthorized'), {
      response: { status: 401 },
    });
    await assert.rejects(
      api.get('/dashboard', {
        adapter: async (config) => {
          protectedError.config = config;
          throw protectedError;
        },
      }),
      (error) => error === protectedError,
    );
    assert.equal(removedToken, true);
    assert.equal(destination, '/login');
  } finally {
    await vite.close();
    if (previousWindow) {
      Object.defineProperty(globalThis, 'window', previousWindow);
    } else {
      delete globalThis.window;
    }
    if (previousStorage) {
      Object.defineProperty(globalThis, 'localStorage', previousStorage);
    } else {
      delete globalThis.localStorage;
    }
  }
});
