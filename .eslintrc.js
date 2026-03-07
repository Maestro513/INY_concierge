module.exports = {
  root: true,
  ignorePatterns: ['admin/', 'backend/'],
  extends: ['expo', 'prettier'],
  plugins: ['prettier'],
  globals: {
    setTimeout: 'readonly',
    clearTimeout: 'readonly',
    setInterval: 'readonly',
    clearInterval: 'readonly',
    AbortController: 'readonly',
    __DEV__: 'readonly',
    btoa: 'readonly',
    atob: 'readonly',
  },
  rules: {
    'prettier/prettier': 'warn',
    'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
    'no-console': 'off',
  },
  overrides: [
    {
      files: ['__tests__/**/*.js', '**/*.test.js', '**/*.spec.js', 'jest.setup.js'],
      env: {
        jest: true,
      },
    },
  ],
};
