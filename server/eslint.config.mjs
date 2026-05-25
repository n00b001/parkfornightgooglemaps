import js from "@eslint/js";

export default [
  js.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        __dirname: "readonly",
        __filename: "readonly",
        Buffer: "readonly",
        console: "readonly",
        module: "readonly",
        process: "readonly",
        require: "readonly",
        setImmediate: "readonly",
        setTimeout: "readonly",
        setInterval: "readonly",
        clearTimeout: "readonly",
        clearInterval: "readonly",
      },
    },
    rules: {
      "no-unused-vars": ["error", { argsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" }],
      "no-useless-catch": "error",
    },
  },
  {
    ignores: ["node_modules/", "tests/"],
  },
];
