import React from 'react';
import { Activity, ArrowRight, Sparkles } from 'lucide-react';

import FinancialNetworkBackground from '../components/FinancialNetworkBackground.jsx';
import MessageBubble from '../components/MessageBubble.jsx';
import {
  capabilityCards,
  chatPromptChips,
  heroReportMessage,
  productPromptChips,
  promptExamples,
  trustStatements,
  workflowSteps,
} from '../data/landingContent.js';

export default function LandingPage({ navigate }) {
  function scrollToExamples() {
    document.querySelector('#example-questions')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  return (
    <div className="landing-page">
      <section className="hero-section">
        <FinancialNetworkBackground />

        <div className="hero-copy">
          <div className="eyebrow">
            <Sparkles size={16} />
            <span>Agentic public-company research</span>
          </div>
          <h1>Public company research. Structured. Fast. Analyst-grade.</h1>
          <p>
            Ask financial questions. Get back investment-style reports powered by real data
            and AI analysis.
          </p>
          <div className="hero-actions">
            <button className="primary-action" type="button" onClick={() => navigate('/chat')}>
              <span>Start Analysis</span>
              <ArrowRight size={18} />
            </button>
            <button className="ghost-action" type="button" onClick={scrollToExamples}>
              Try a Sample Thesis
            </button>
          </div>
        </div>

        <div className="hero-response" aria-label="Sample analysis response">
          <MessageBubble message={heroReportMessage} />
        </div>
      </section>

      <div className="section-divider" aria-hidden="true" />

      <section className="product-preview-section" id="product-preview">
        <div className="preview-flow">
          <div className="chat-preview-window" aria-label="Chat interface preview">
            <div className="preview-topbar">
              <span>Research Chat</span>
              <strong>Connected</strong>
            </div>
            <div className="preview-thread">
              <div className="preview-message user">Build an investor thesis for AAPL.</div>
              <article className="preview-report">
                <h3>Apple Investment Report</h3>
                <h4>Executive View</h4>
                <p>
                  Apple combines a premium hardware base with services-driven margin support,
                  but the valuation still depends on sustained free cash flow growth.
                </p>
                <h4>Key Findings</h4>
                <ul>
                  <li>Revenue quality improves as services become a larger mix.</li>
                  <li>Capital returns remain central to the shareholder story.</li>
                  <li>Hardware cycles are the main near-term watch item.</li>
                </ul>
              </article>
            </div>
          </div>

          <div className="preview-ask">
            <div className="section-heading">
              <span>Product Preview</span>
              <h2>From question to report in seconds</h2>
            </div>
            <span className="preview-ask-label">
              <Sparkles size={15} />
              You ask
            </span>
            <div className="prompt-rotator" aria-label="Example inputs">
              {productPromptChips.map((prompt, index) => (
                // Stagger evenly across the 6s cycle so only one bubble shows at a time.
                <span key={prompt} style={{ animationDelay: `${(index * 6) / productPromptChips.length}s` }}>
                  {prompt}
                </span>
              ))}
            </div>
            <p className="preview-ask-hint">
              Ask in plain language — tickers, comparisons, valuations, or risks. The agent routes
              the data and writes the report.
            </p>
            <div className="preview-ask-chips">
              {chatPromptChips.map((chip) => (
                <button key={chip} type="button" onClick={() => navigate('/chat')}>
                  <span>{chip}</span>
                  <ArrowRight size={14} />
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="capability-section" id="capabilities">
        <div className="section-heading">
          <span>Core Capabilities</span>
          <h2>Everything you need for a first-pass analysis</h2>
        </div>

        <div className="capability-grid">
          {capabilityCards.map((item) => (
            <article className="capability-card" key={item.title}>
              <div className="capability-label">
                <item.icon size={18} />
                <span>{item.label}</span>
              </div>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </section>

      <div className="section-divider" aria-hidden="true" />

      <section className="workflow-section">
        <div className="section-heading">
          <span>Workflow</span>
          <h2>How it works</h2>
        </div>

        <div className="timeline">
          {workflowSteps.map((step) => (
            <article className="timeline-step" key={step.number}>
              <span>{step.number}</span>
              <h3>{step.title}</h3>
              <p>{step.body}</p>
            </article>
          ))}
        </div>

        <div className="section-action">
          <button className="primary-action" type="button" onClick={() => navigate('/chat')}>
            <span>Start Analysis</span>
            <ArrowRight size={18} />
          </button>
        </div>
      </section>

      <section className="example-section" id="example-questions">
        <div className="section-heading">
          <span>Example Questions</span>
          <h2>What would you like to research?</h2>
        </div>

        <div className="example-grid">
          {promptExamples.map((question) => (
            <button key={question} type="button" onClick={() => navigate('/chat')}>
              <span>{question}</span>
              <ArrowRight size={17} />
            </button>
          ))}
        </div>

      </section>

      <footer className="site-footer">
        <div className="footer-trust">
          <div className="trust-grid">
            {trustStatements.map((item) => (
              <article key={item.title}>
                <item.icon size={18} />
                <span>{item.title}</span>
              </article>
            ))}
          </div>
          <p>
            Baboon Analyst is a research tool. All information is sourced from public filings and market data.
            This platform does not provide personalized investment advice. Always do your own due diligence.
          </p>
        </div>

        <div className="footer-main">
          <button className="footer-brand" type="button" onClick={() => navigate('/')}>
            <Activity size={19} />
            <span>Baboon Analyst</span>
          </button>
          <small>Copyright 2026 Baboon Analyst. All rights reserved.</small>
        </div>
      </footer>
    </div>
  );
}
