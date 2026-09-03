module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
    node: true,
  },
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
  },
  extends: ["plugin:vue/vue3-essential", "@vue/eslint-config-prettier"],
  rules: {
    "no-undef": "off",
    "no-unused-vars": "off",
    "vue/no-unused-vars": "off",
    "vue/multi-word-component-names": "off",
  },
  ignorePatterns: ["dist/", "node_modules/"],
};
