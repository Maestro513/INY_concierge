const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');
const https = require('https');

const TARGET_STATES = [
  'Alaska', 'Hawaii', 'Maryland', 'Minnesota', 'Nebraska',
  'New Mexico', 'North Carolina', 'North Dakota', 'Rhode Island',
  'South Dakota', 'Vermont'
];

const BASE_URL = 'https://www.medicareadvantage.com';
const DOWNLOAD_DIR = path.join(__dirname, '..', 'sob_pdfs');
const DELAY_MS = 2000; // delay between page loads to be polite

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function downloadFile(url, filepath) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(filepath);
    https.get(url, { headers: { 'User-Agent': 'Mozilla/5.0' } }, (res) => {
      if (res.statusCode === 301 || res.statusCode === 302) {
        file.close();
        fs.unlinkSync(filepath);
        return downloadFile(res.headers.location, filepath).then(resolve).catch(reject);
      }
      res.pipe(file);
      file.on('finish', () => { file.close(); resolve(); });
    }).on('error', (err) => {
      fs.unlinkSync(filepath);
      reject(err);
    });
  });
}

async function collectPlanUrls(page, state) {
  const stateSlug = state.toLowerCase().replace(/\s+/g, '-');
  const searchUrl = `${BASE_URL}/find-plans?state=${encodeURIComponent(state)}&carrier=UnitedHealthcare`;

  console.log(`\n--- Searching plans in ${state} ---`);
  console.log(`URL: ${searchUrl}`);

  await page.goto(searchUrl, { waitUntil: 'networkidle2', timeout: 30000 });
  await sleep(DELAY_MS);

  const planUrls = new Set();

  // Try to collect all plan links, handling pagination
  let hasMore = true;
  while (hasMore) {
    const links = await page.$$eval('a[href*="/plans/"]', (anchors) =>
      anchors
        .map(a => a.href)
        .filter(href => href.includes('/plans/') && (href.includes('uhc') || href.includes('united') || href.includes('aarp')))
    );

    links.forEach(link => planUrls.add(link));

    // Check for a "next page" or "load more" button
    const nextBtn = await page.$('button[aria-label="Next page"], a[aria-label="Next page"], [class*="next"], [class*="load-more"]');
    if (nextBtn) {
      await nextBtn.click();
      await sleep(DELAY_MS);
    } else {
      hasMore = false;
    }
  }

  console.log(`Found ${planUrls.size} UHC plan(s) in ${state}`);
  return Array.from(planUrls);
}

async function getSobPdfUrl(page, planUrl) {
  try {
    await page.goto(planUrl, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(DELAY_MS);

    // Scroll to the bottom to trigger any lazy loading
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await sleep(1500);

    // Look for Summary of Benefits PDF link
    const pdfUrl = await page.evaluate(() => {
      const allLinks = Array.from(document.querySelectorAll('a'));
      const sobLink = allLinks.find(a => {
        const text = (a.textContent || '').toLowerCase();
        const href = (a.href || '').toLowerCase();
        return (text.includes('summary of benefits') || text.includes('sob')) &&
               (href.includes('.pdf') || href.includes('summary') || href.includes('benefit'));
      });
      return sobLink ? sobLink.href : null;
    });

    return pdfUrl;
  } catch (err) {
    console.error(`  Error loading ${planUrl}: ${err.message}`);
    return null;
  }
}

async function main() {
  if (!fs.existsSync(DOWNLOAD_DIR)) {
    fs.mkdirSync(DOWNLOAD_DIR, { recursive: true });
  }

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');

  const results = { success: [], failed: [], noSob: [] };

  for (const state of TARGET_STATES) {
    const planUrls = await collectPlanUrls(page, state);

    for (const planUrl of planUrls) {
      const planSlug = planUrl.split('/plans/')[1] || 'unknown';
      console.log(`  Checking: ${planSlug}`);

      const pdfUrl = await getSobPdfUrl(page, planUrl);

      if (!pdfUrl) {
        console.log(`    No SOB PDF found`);
        results.noSob.push({ state, planUrl });
        continue;
      }

      const filename = `${planSlug.replace(/[^a-z0-9-]/gi, '_')}_SOB.pdf`;
      const filepath = path.join(DOWNLOAD_DIR, filename);

      try {
        console.log(`    Downloading: ${pdfUrl}`);
        await downloadFile(pdfUrl, filepath);
        console.log(`    Saved: ${filename}`);
        results.success.push({ state, planUrl, pdfUrl, filename });
      } catch (err) {
        console.error(`    Download failed: ${err.message}`);
        results.failed.push({ state, planUrl, pdfUrl, error: err.message });
      }
    }
  }

  await browser.close();

  // Save results summary
  const summaryPath = path.join(DOWNLOAD_DIR, '_download_summary.json');
  fs.writeFileSync(summaryPath, JSON.stringify(results, null, 2));

  console.log('\n=== DOWNLOAD SUMMARY ===');
  console.log(`Success: ${results.success.length}`);
  console.log(`No SOB found: ${results.noSob.length}`);
  console.log(`Failed: ${results.failed.length}`);
  console.log(`Summary saved to: ${summaryPath}`);
  console.log(`PDFs saved to: ${DOWNLOAD_DIR}`);
}

main().catch(console.error);
