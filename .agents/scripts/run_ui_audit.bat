@echo off
echo Running automated UI/UX and Accessibility audit via Lighthouse...
npx -y lighthouse http://127.0.0.1:8050 --output html --output-path ./scratch/lighthouse_report.html --view --chrome-flags="--headless"
echo Report saved to ./scratch/lighthouse_report.html
