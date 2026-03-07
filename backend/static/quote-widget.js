/**
 * Insurance 'N You — Quoting Widget
 * Embeddable on Webflow state pages.
 * Shows Medicare Advantage plans (from CMS DB) and Under-65 ACA Marketplace plans.
 */
(function () {
  "use strict";

  const API_BASE =
    window.INY_API_BASE || "https://api.insurancenyou.com";
  const QUOTE_URL =
    window.INY_QUOTE_URL || "https://www.insurancenyou.com/the-perfect-policy";

  // Detect state from page URL (e.g., /health-insurance-alabama → AL)
  const STATE_MAP = {
    alabama: "AL", alaska: "AK", arizona: "AZ", arkansas: "AR",
    california: "CA", colorado: "CO", connecticut: "CT", delaware: "DE",
    florida: "FL", georgia: "GA", hawaii: "HI", idaho: "ID",
    illinois: "IL", indiana: "IN", iowa: "IA", kansas: "KS",
    kentucky: "KY", louisiana: "LA", maine: "ME", maryland: "MD",
    massachusetts: "MA", michigan: "MI", minnesota: "MN", mississippi: "MS",
    missouri: "MO", montana: "MT", nebraska: "NE", nevada: "NV",
    "new-hampshire": "NH", "new-jersey": "NJ", "new-mexico": "NM",
    "new-york": "NY", "north-carolina": "NC", "north-dakota": "ND",
    ohio: "OH", oklahoma: "OK", oregon: "OR", pennsylvania: "PA",
    "rhode-island": "RI", "south-carolina": "SC", "south-dakota": "SD",
    tennessee: "TN", texas: "TX", utah: "UT", vermont: "VT",
    virginia: "VA", washington: "WA", "west-virginia": "WV",
    wisconsin: "WI", wyoming: "WY",
  };

  const STATE_NAMES = {};
  Object.entries(STATE_MAP).forEach(([name, code]) => {
    STATE_NAMES[code] = name
      .split("-")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  });

  function detectState() {
    const path = window.location.pathname.toLowerCase();
    const match = path.match(/health-insurance-(.+?)(?:\/|$)/);
    if (match) {
      const stateName = match[1];
      return STATE_MAP[stateName] || null;
    }
    return null;
  }

  const pageState = detectState();

  // ── Styles ──────────────────────────────────────────────────────────────────
  const STYLES = `
    .iny-quote-widget {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      max-width: 100%;
      color: #1a1a2e;
    }
    .iny-quote-widget * { box-sizing: border-box; margin: 0; padding: 0; }

    .iny-toggle-wrap {
      display: flex;
      background: #f0f0f5;
      border-radius: 12px;
      padding: 4px;
      margin-bottom: 20px;
    }
    .iny-toggle-btn {
      flex: 1;
      padding: 12px 16px;
      border: none;
      border-radius: 10px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      background: transparent;
      color: #666;
      transition: all 0.2s ease;
    }
    .iny-toggle-btn.active {
      background: #1a1a2e;
      color: #fff;
      box-shadow: 0 2px 8px rgba(26, 26, 46, 0.2);
    }

    .iny-form-section {
      margin-bottom: 20px;
    }
    .iny-form-row {
      display: flex;
      gap: 10px;
      margin-bottom: 10px;
    }
    .iny-form-row > * { flex: 1; }

    .iny-label {
      display: block;
      font-size: 12px;
      font-weight: 600;
      color: #555;
      margin-bottom: 4px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .iny-input {
      width: 100%;
      padding: 10px 14px;
      border: 2px solid #e0e0e8;
      border-radius: 8px;
      font-size: 15px;
      color: #1a1a2e;
      outline: none;
      transition: border-color 0.2s;
    }
    .iny-input:focus { border-color: #00c853; }
    .iny-input::placeholder { color: #aaa; }

    .iny-search-btn {
      width: 100%;
      padding: 14px;
      background: linear-gradient(135deg, #00c853 0%, #00a844 100%);
      color: #fff;
      border: none;
      border-radius: 10px;
      font-size: 16px;
      font-weight: 700;
      cursor: pointer;
      transition: transform 0.1s, box-shadow 0.2s;
    }
    .iny-search-btn:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(0, 200, 83, 0.3);
    }
    .iny-search-btn:disabled {
      opacity: 0.6;
      cursor: not-allowed;
      transform: none;
    }

    .iny-county-select {
      background: #fff8e1;
      border: 1px solid #ffd54f;
      border-radius: 8px;
      padding: 12px;
      margin-bottom: 16px;
    }
    .iny-county-select p {
      font-size: 13px;
      color: #6d5e00;
      margin-bottom: 8px;
    }

    .iny-results-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }
    .iny-results-count {
      font-size: 14px;
      color: #888;
    }

    .iny-loading {
      text-align: center;
      padding: 40px 20px;
      color: #888;
    }
    .iny-spinner {
      width: 36px;
      height: 36px;
      border: 3px solid #e0e0e8;
      border-top-color: #00c853;
      border-radius: 50%;
      animation: iny-spin 0.7s linear infinite;
      margin: 0 auto 12px;
    }
    @keyframes iny-spin { to { transform: rotate(360deg); } }

    .iny-error {
      background: #fff0f0;
      border: 1px solid #ffcdd2;
      border-radius: 8px;
      padding: 16px;
      color: #c62828;
      font-size: 14px;
      text-align: center;
    }

    .iny-plans-list {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .iny-plan-card {
      background: #fff;
      border: 1px solid #e8e8f0;
      border-radius: 14px;
      padding: 20px;
      transition: box-shadow 0.2s, border-color 0.2s;
      position: relative;
      overflow: hidden;
    }
    .iny-plan-card:hover {
      border-color: #00c853;
      box-shadow: 0 4px 20px rgba(0, 200, 83, 0.1);
    }

    .iny-card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 12px;
    }
    .iny-card-org {
      font-size: 12px;
      color: #888;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }
    .iny-card-name {
      font-size: 16px;
      font-weight: 700;
      color: #1a1a2e;
      margin-top: 2px;
      line-height: 1.3;
    }
    .iny-card-premium {
      text-align: right;
      flex-shrink: 0;
      margin-left: 16px;
    }
    .iny-premium-amount {
      font-size: 28px;
      font-weight: 800;
      color: #00a844;
      line-height: 1;
    }
    .iny-premium-label {
      font-size: 11px;
      color: #888;
      margin-top: 2px;
    }

    .iny-card-badges {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }
    .iny-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 4px 10px;
      border-radius: 20px;
      font-size: 11px;
      font-weight: 600;
    }
    .iny-badge-type {
      background: #e8eaf6;
      color: #3949ab;
    }
    .iny-badge-metal {
      color: #fff;
    }
    .iny-badge-metal.bronze { background: #8d6e63; }
    .iny-badge-metal.silver { background: #78909c; }
    .iny-badge-metal.gold { background: #f9a825; }
    .iny-badge-metal.platinum { background: #5c6bc0; }
    .iny-badge-metal.catastrophic { background: #e53935; }
    .iny-badge-giveback {
      background: #e8f5e9;
      color: #2e7d32;
    }
    .iny-badge-snp {
      background: #fff3e0;
      color: #e65100;
    }

    .iny-card-benefits {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
      gap: 8px;
      margin-bottom: 14px;
    }
    .iny-benefit-item {
      background: #f8f8fc;
      border-radius: 8px;
      padding: 8px 10px;
    }
    .iny-benefit-label {
      font-size: 10px;
      color: #888;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }
    .iny-benefit-value {
      font-size: 14px;
      font-weight: 700;
      color: #1a1a2e;
      margin-top: 1px;
    }
    .iny-benefit-value.free { color: #00a844; }

    .iny-card-extras {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }
    .iny-extra-tag {
      display: flex;
      align-items: center;
      gap: 3px;
      font-size: 11px;
      color: #555;
    }
    .iny-extra-tag svg { width: 14px; height: 14px; fill: #00c853; }

    .iny-card-cta {
      display: inline-block;
      padding: 10px 24px;
      background: #1a1a2e;
      color: #fff;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      text-decoration: none;
      transition: background 0.2s;
    }
    .iny-card-cta:hover { background: #2d2d4e; }

    .iny-no-results {
      text-align: center;
      padding: 40px 20px;
      color: #888;
    }
    .iny-no-results p { margin-bottom: 8px; }

    .iny-marketplace-note {
      background: #e8f5e9;
      border-radius: 8px;
      padding: 12px 16px;
      font-size: 13px;
      color: #2e7d32;
      margin-bottom: 16px;
      line-height: 1.5;
    }

    @media (max-width: 600px) {
      .iny-form-row { flex-direction: column; }
      .iny-card-header { flex-direction: column; }
      .iny-card-premium { text-align: left; margin-left: 0; margin-top: 8px; }
      .iny-card-benefits { grid-template-columns: repeat(2, 1fr); }
    }
  `;

  // ── Check Icon SVG ──────────────────────────────────────────────────────────
  const CHECK_SVG =
    '<svg viewBox="0 0 20 20"><path d="M16.7 5.3a1 1 0 010 1.4l-8 8a1 1 0 01-1.4 0l-4-4a1 1 0 111.4-1.4L8 12.6l7.3-7.3a1 1 0 011.4 0z"/></svg>';

  // ── Widget Class ────────────────────────────────────────────────────────────
  class QuoteWidget {
    constructor(container) {
      this.container = container;
      this.mode = "medicare"; // "medicare" or "u65"
      this.plans = [];
      this.loading = false;
      this.error = null;
      this.counties = null;
      this.selectedFips = null;
      this.inject();
      this.render();
    }

    inject() {
      if (!document.getElementById("iny-quote-styles")) {
        const style = document.createElement("style");
        style.id = "iny-quote-styles";
        style.textContent = STYLES;
        document.head.appendChild(style);
      }
      this.container.classList.add("iny-quote-widget");
    }

    render() {
      const html = `
        ${this.renderToggle()}
        ${this.renderForm()}
        ${this.renderResults()}
      `;
      this.container.innerHTML = html;
      this.bind();
    }

    renderToggle() {
      return `
        <div class="iny-toggle-wrap">
          <button class="iny-toggle-btn ${this.mode === "medicare" ? "active" : ""}"
                  data-mode="medicare">Medicare (65+)</button>
          <button class="iny-toggle-btn ${this.mode === "u65" ? "active" : ""}"
                  data-mode="u65">Under 65</button>
        </div>
      `;
    }

    renderForm() {
      const isU65 = this.mode === "u65";
      return `
        <div class="iny-form-section">
          <div class="iny-form-row">
            <div>
              <label class="iny-label">Zip Code</label>
              <input class="iny-input" id="iny-zip" type="text" inputmode="numeric"
                     pattern="[0-9]{5}" maxlength="5" placeholder="Enter zip code"
                     value="${this._lastZip || ""}">
            </div>
            ${isU65 ? `
            <div>
              <label class="iny-label">Age</label>
              <input class="iny-input" id="iny-age" type="number" min="0" max="64"
                     placeholder="Your age" value="${this._lastAge || ""}">
            </div>
            ` : ""}
          </div>
          ${isU65 ? `
          <div class="iny-form-row">
            <div>
              <label class="iny-label">Household Income (annual)</label>
              <input class="iny-input" id="iny-income" type="number" min="0"
                     placeholder="e.g. 50000" value="${this._lastIncome || ""}">
            </div>
            <div>
              <label class="iny-label">Household Size</label>
              <input class="iny-input" id="iny-hhsize" type="number" min="1" max="10"
                     placeholder="1" value="${this._lastHHSize || "1"}">
            </div>
          </div>
          ` : ""}
          ${this.renderCountySelect()}
          <button class="iny-search-btn" id="iny-search-btn" ${this.loading ? "disabled" : ""}>
            ${this.loading ? "Searching..." : "Find Plans"}
          </button>
        </div>
      `;
    }

    renderCountySelect() {
      if (!this.counties || this.counties.length <= 1) return "";
      return `
        <div class="iny-county-select">
          <p>This zip code covers multiple counties. Please select yours:</p>
          <select class="iny-input" id="iny-county-select">
            ${this.counties.map((c) =>
              `<option value="${c.fips}" ${c.fips === this.selectedFips ? "selected" : ""}>
                ${c.name}, ${c.state}
              </option>`
            ).join("")}
          </select>
        </div>
      `;
    }

    renderResults() {
      if (this.loading) {
        return `
          <div class="iny-loading">
            <div class="iny-spinner"></div>
            <p>Searching for the best plans...</p>
          </div>
        `;
      }
      if (this.error) {
        return `<div class="iny-error">${this.esc(this.error)}</div>`;
      }
      if (!this.plans.length) return "";

      const isU65 = this.mode === "u65";
      return `
        ${isU65 ? `
        <div class="iny-marketplace-note">
          Showing ACA Marketplace plans from Healthcare.gov. Subsidies are estimated
          based on the income provided. Final eligibility is determined during enrollment.
        </div>
        ` : ""}
        <div class="iny-results-header">
          <span class="iny-results-count">${this.plans.length} plan${this.plans.length !== 1 ? "s" : ""} found</span>
        </div>
        <div class="iny-plans-list">
          ${this.plans.map((p) => this.renderPlanCard(p)).join("")}
        </div>
      `;
    }

    renderPlanCard(plan) {
      const isMedicare = plan.type === "medicare";
      const premium = plan.monthly_premium;
      const premiumDisplay =
        premium === null || premium === undefined
          ? "Call"
          : premium === 0
          ? "$0"
          : `$${Number(premium).toFixed(0)}`;
      const deductible = plan.annual_deductible;
      const deductibleDisplay =
        deductible === null || deductible === undefined
          ? "—"
          : deductible === 0
          ? "$0"
          : `$${Number(deductible).toLocaleString()}`;

      // Badges
      let badges = "";
      if (plan.plan_type) {
        badges += `<span class="iny-badge iny-badge-type">${this.esc(plan.plan_type)}</span>`;
      }
      if (plan.metal_level) {
        const ml = this.esc(plan.metal_level.toLowerCase());
        badges += `<span class="iny-badge iny-badge-metal ${ml}">${this.esc(plan.metal_level)}</span>`;
      }
      if (plan.part_b_giveback) {
        badges += `<span class="iny-badge iny-badge-giveback">Part B Giveback ${this.esc(plan.part_b_giveback)}/mo</span>`;
      }
      if (plan.snp_type && plan.snp_type !== "No" && plan.snp_type.trim()) {
        badges += `<span class="iny-badge iny-badge-snp">SNP</span>`;
      }
      if (plan.hsa_eligible) {
        badges += `<span class="iny-badge iny-badge-giveback">HSA Eligible</span>`;
      }

      // Benefits grid
      let benefits = "";
      benefits += this.benefitItem("Deductible", deductibleDisplay);
      if (plan.pcp_copay)
        benefits += this.benefitItem("PCP Visit", this.esc(plan.pcp_copay));
      if (plan.specialist_copay)
        benefits += this.benefitItem("Specialist", this.esc(plan.specialist_copay));
      if (plan.moop)
        benefits += this.benefitItem(
          "Max Out-of-Pocket",
          `$${Number(plan.moop).toLocaleString()}`
        );

      // Extra tags
      let extras = "";
      if (plan.has_dental) extras += this.extraTag("Dental");
      if (plan.has_vision) extras += this.extraTag("Vision");
      if (plan.has_otc) {
        const otcLabel = plan.otc_amount ? `OTC ${this.esc(plan.otc_amount)}` : "OTC";
        extras += this.extraTag(otcLabel);
      }
      if (plan.dental_max)
        extras += this.extraTag(`Dental Max ${this.esc(plan.dental_max)}`);
      if (plan.quality_rating)
        extras += this.extraTag(`${this.esc(plan.quality_rating)} Stars`);

      // Premium display for U65 with credit
      let premiumSection = "";
      if (!isMedicare && plan.premium_with_credit !== null && plan.premium_with_credit !== undefined && plan.premium_with_credit !== premium) {
        premiumSection = `
          <div class="iny-card-premium">
            <div class="iny-premium-amount">$${Number(plan.premium_with_credit).toFixed(0)}</div>
            <div class="iny-premium-label">w/ subsidy /mo</div>
            <div style="font-size:11px;color:#aaa;text-decoration:line-through;margin-top:2px;">$${Number(premium).toFixed(0)}/mo</div>
          </div>
        `;
      } else {
        premiumSection = `
          <div class="iny-card-premium">
            <div class="iny-premium-amount">${premiumDisplay}</div>
            <div class="iny-premium-label">/month</div>
          </div>
        `;
      }

      const planId = plan.plan_number || plan.plan_id || "";
      const ctaUrl = `${QUOTE_URL}?plan=${encodeURIComponent(planId)}&zip=${encodeURIComponent(this._lastZip || "")}`;

      return `
        <div class="iny-plan-card">
          <div class="iny-card-header">
            <div>
              <div class="iny-card-org">${this.esc(plan.org_name)}</div>
              <div class="iny-card-name">${this.esc(plan.plan_name)}</div>
            </div>
            ${premiumSection}
          </div>
          ${badges ? `<div class="iny-card-badges">${badges}</div>` : ""}
          <div class="iny-card-benefits">${benefits}</div>
          ${extras ? `<div class="iny-card-extras">${extras}</div>` : ""}
          <a class="iny-card-cta" href="${ctaUrl}" target="_blank" rel="noopener">
            View Plan Details
          </a>
        </div>
      `;
    }

    benefitItem(label, value) {
      const isFree = value === "$0";
      return `
        <div class="iny-benefit-item">
          <div class="iny-benefit-label">${this.esc(label)}</div>
          <div class="iny-benefit-value ${isFree ? "free" : ""}">${this.esc(value)}</div>
        </div>
      `;
    }

    extraTag(label) {
      return `<span class="iny-extra-tag">${CHECK_SVG} ${this.esc(label)}</span>`;
    }

    esc(str) {
      const div = document.createElement("div");
      div.textContent = str || "";
      return div.innerHTML;
    }

    bind() {
      // Toggle buttons
      this.container.querySelectorAll(".iny-toggle-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          this.mode = btn.dataset.mode;
          this.plans = [];
          this.error = null;
          this.counties = null;
          this.selectedFips = null;
          this.render();
        });
      });

      // Search button
      const searchBtn = this.container.querySelector("#iny-search-btn");
      if (searchBtn) {
        searchBtn.addEventListener("click", () => this.search());
      }

      // Enter key on zip input
      const zipInput = this.container.querySelector("#iny-zip");
      if (zipInput) {
        zipInput.addEventListener("keydown", (e) => {
          if (e.key === "Enter") this.search();
        });
      }

      // County select
      const countySelect = this.container.querySelector("#iny-county-select");
      if (countySelect) {
        countySelect.addEventListener("change", (e) => {
          this.selectedFips = e.target.value;
        });
      }
    }

    async search() {
      const zipInput = this.container.querySelector("#iny-zip");
      const zip = zipInput ? zipInput.value.trim() : "";
      if (!zip || zip.length !== 5) {
        this.error = "Please enter a valid 5-digit zip code.";
        this.plans = [];
        this.render();
        return;
      }

      this._lastZip = zip;

      // U65 fields
      if (this.mode === "u65") {
        const ageInput = this.container.querySelector("#iny-age");
        const incomeInput = this.container.querySelector("#iny-income");
        const hhInput = this.container.querySelector("#iny-hhsize");
        this._lastAge = ageInput ? ageInput.value : "";
        this._lastIncome = incomeInput ? incomeInput.value : "";
        this._lastHHSize = hhInput ? hhInput.value : "1";
      }

      this.loading = true;
      this.error = null;
      this.plans = [];
      this.render();

      try {
        let url;
        if (this.mode === "medicare") {
          url = `${API_BASE}/quote/medicare?zip=${zip}&limit=20`;
        } else {
          const age = this._lastAge || "30";
          const income = this._lastIncome || "";
          const hhsize = this._lastHHSize || "1";
          url = `${API_BASE}/quote/marketplace?zip=${zip}&age=${age}&limit=20`;
          if (income) url += `&income=${income}`;
          if (hhsize) url += `&household_size=${hhsize}`;
          if (this.selectedFips) url += `&fips=${this.selectedFips}`;
        }

        const resp = await fetch(url);
        if (!resp.ok) {
          const errData = await resp.json().catch(() => ({}));
          throw new Error(errData.detail || `Request failed (${resp.status})`);
        }
        const data = await resp.json();

        // Handle multi-county
        if (data.all_counties && data.all_counties.length > 1) {
          this.counties = data.all_counties;
          if (!this.selectedFips) {
            this.selectedFips = data.all_counties[0].fips;
          }
        }

        this.plans = data.plans || [];
        if (!this.plans.length) {
          this.error = "No plans found for this zip code. Try a different zip or coverage type.";
        }
      } catch (err) {
        this.error = err.message || "Something went wrong. Please try again.";
        this.plans = [];
      } finally {
        this.loading = false;
        this.render();
      }
    }
  }

  // ── Auto-init ───────────────────────────────────────────────────────────────
  function init() {
    const targets = document.querySelectorAll(
      '[data-iny-quote], #iny-quote-widget, .iny-quote-widget-target'
    );
    targets.forEach((el) => {
      if (!el._inyWidget) {
        el._inyWidget = new QuoteWidget(el);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Expose for manual init
  window.INYQuoteWidget = QuoteWidget;
})();
