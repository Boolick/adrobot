import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';
import eslintConfigPrettier from 'eslint-config-prettier';
import boundaries from 'eslint-plugin-boundaries';

export default tseslint.config(
  { ignores: ['dist/**', 'node_modules/**', 'coverage/**', '*.d.ts'] },
  // Base configuration
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended, eslintConfigPrettier],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      // 1. Strict TypeScript (No Any, strict checks, consistent types)
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/consistent-type-imports': 'error',

      // 2. Airbnb Style & Clean Code
      eqeqeq: ['error', 'always', { null: 'ignore' }],
      'prefer-const': 'error',
      'no-var': 'error',
      curly: ['error', 'all'],
      'no-duplicate-imports': 'error',
      'no-unneeded-ternary': 'error',
      'no-nested-ternary': 'warn',
      'prefer-template': 'warn',
      'no-console': ['warn', { allow: ['warn', 'error', 'info'] }],

      // 3. File & Line Limits
      'max-lines': ['error', { max: 300, skipBlankLines: true, skipComments: true }],
      'max-len': [
        'warn',
        {
          code: 120,
          ignoreUrls: true,
          ignoreStrings: true,
          ignoreTemplateLiterals: true,
          ignoreComments: true,
          ignoreRegExpLiterals: true,
        },
      ],

      // 4. React Specifics
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },

  // 5. Architectural Boundaries via eslint-plugin-boundaries (v7 API)
  {
    files: ['src/**/*.{ts,tsx}'],
    plugins: {
      boundaries,
    },
    settings: {
      'boundaries/include': ['src/**/*'],
      'boundaries/elements': [
        { type: 'app', pattern: 'src/app/**' },
        { type: 'pages', pattern: 'src/pages/**' },
        { type: 'widgets', pattern: 'src/widgets/**' },
        { type: 'features', pattern: 'src/features/**' },
        { type: 'entities', pattern: 'src/entities/**' },
        { type: 'shared', pattern: 'src/shared/**' },
      ],
    },
    rules: {
      'boundaries/dependencies': [
        'error',
        {
          default: 'disallow',
          policies: [
            {
              from: { element: { type: 'app' } },
              allow: [
                { to: { element: { type: 'pages' } } },
                { to: { element: { type: 'widgets' } } },
                { to: { element: { type: 'features' } } },
                { to: { element: { type: 'entities' } } },
                { to: { element: { type: 'shared' } } },
              ],
            },
            {
              from: { element: { type: 'pages' } },
              allow: [
                { to: { element: { type: 'widgets' } } },
                { to: { element: { type: 'features' } } },
                { to: { element: { type: 'entities' } } },
                { to: { element: { type: 'shared' } } },
              ],
            },
            {
              from: { element: { type: 'widgets' } },
              allow: [
                { to: { element: { type: 'features' } } },
                { to: { element: { type: 'entities' } } },
                { to: { element: { type: 'shared' } } },
              ],
            },
            {
              from: { element: { type: 'features' } },
              allow: [
                { to: { element: { type: 'entities' } } },
                { to: { element: { type: 'shared' } } },
              ],
            },
            {
              from: { element: { type: 'entities' } },
              allow: [{ to: { element: { type: 'shared' } } }],
            },
            {
              from: { element: { type: 'shared' } },
              allow: [],
            },
          ],
        },
      ],
    },
  },

  // 6. FSD Layer Import Hierarchy (Strict Boundaries via restricted imports from docs/temp/eslint.config.js)
  // Shared layer cannot import from entities, features, widgets, pages, app
  {
    files: ['src/shared/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@/entities/**', '@/features/**', '@/widgets/**', '@/pages/**', '@/app/**'],
              message:
                'FSD Hierarchy Violation: "shared" layer cannot import from higher layers (entities, features, widgets, pages, app).',
            },
            {
              group: [
                '../*/entities/**',
                '../*/features/**',
                '../*/widgets/**',
                '../*/pages/**',
                '../*/app/**',
              ],
              message:
                'FSD Hierarchy Violation: "shared" layer cannot import from higher layers via relative paths.',
            },
          ],
        },
      ],
    },
  },

  // Entities layer cannot import from features, widgets, pages, app
  {
    files: ['src/entities/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@/features/**', '@/widgets/**', '@/pages/**', '@/app/**'],
              message:
                'FSD Hierarchy Violation: "entities" layer cannot import from features, widgets, pages, or app.',
            },
            {
              group: ['../*/features/**', '../*/widgets/**', '../*/pages/**', '../*/app/**'],
              message:
                'FSD Hierarchy Violation: "entities" layer cannot import from features, widgets, pages, or app via relative paths.',
            },
          ],
        },
      ],
    },
  },

  // Features layer cannot import from widgets, pages, app
  {
    files: ['src/features/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@/widgets/**', '@/pages/**', '@/app/**'],
              message:
                'FSD Hierarchy Violation: "features" layer cannot import from widgets, pages, or app.',
            },
            {
              group: ['../*/widgets/**', '../*/pages/**', '../*/app/**'],
              message:
                'FSD Hierarchy Violation: "features" layer cannot import from widgets, pages, or app via relative paths.',
            },
          ],
        },
      ],
    },
  },

  // Widgets layer cannot import from pages, app
  {
    files: ['src/widgets/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@/pages/**', '@/app/**'],
              message: 'FSD Hierarchy Violation: "widgets" layer cannot import from pages or app.',
            },
            {
              group: ['../*/pages/**', '../*/app/**'],
              message:
                'FSD Hierarchy Violation: "widgets" layer cannot import from pages or app via relative paths.',
            },
          ],
        },
      ],
    },
  },

  // Pages layer cannot import from app
  {
    files: ['src/pages/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@/app/**'],
              message: 'FSD Hierarchy Violation: "pages" layer cannot import from app layer.',
            },
            {
              group: ['../*/app/**'],
              message:
                'FSD Hierarchy Violation: "pages" layer cannot import from app layer via relative paths.',
            },
          ],
        },
      ],
    },
  },
);
