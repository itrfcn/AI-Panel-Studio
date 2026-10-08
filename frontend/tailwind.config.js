/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts}'],
  theme: {
    extend: {
      colors: {
        // 演播厅暗色基调
        studio: {
          bg: '#0f1115',
          panel: '#171a21',
          border: '#2a2f3a',
          accent: '#2A6F97',
        },
      },
      fontFamily: {
        sans: ['"PingFang SC"', '"Microsoft YaHei"', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
