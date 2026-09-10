import globals from 'globals';

// Transitional JS composition shells still need reference checking. Strict TS
// owns the editor contracts/behavior; do not hide missing imports with globals.
export default [{
  files:['src/**/*.js'],
  languageOptions:{ecmaVersion:2022,sourceType:'module',globals:globals.browser},
  rules:{'no-undef':'error','no-unreachable':'error','no-duplicate-imports':'error'}
}];
