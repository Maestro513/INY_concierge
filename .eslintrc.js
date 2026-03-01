module.exports = {
  root: true,
  extends: ['expo', 'prettier'],
  plugins: ['prettier'],
  globals: {
    setTimeout: 'readonly',
    clearTimeout: 'readonly',
    setInterval: 'readonly',
    clearInterval: 'readonly',
    AbortController: 'readonly',
    __DEV__: 'readonly',
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
