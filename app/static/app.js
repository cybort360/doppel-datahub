const state = {
  asset: null,
  currentScreen: 0,
  run: null,
  showingRejected: false,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const DEMO_CONFIG = {
  asset_id: 'healthcare',
  scale: 1,
  seed: 42,
  expiry_days: 30,
  publish_after_generation: true,
};

const REJECTED_EXAMPLE = {
  run_id: 'rejected-example',
  decision: 'REJECTED',
  reasons: [
    '12 complete source rows were reproduced in the synthetic output.',
    '8 direct-identifier values overlap with the source dataset.',
    'Privacy score 42.0 is below the required 100.0 threshold.',
    'Privacy gate failed: patients.exact_row_overlap.',
    'Privacy gate failed: patients.direct_identifier_overlap.',
  ],
  privacy_score: 42.0,
  utility_score: 91.0,
  integrity_score: 100.0,
  fk_integrity: 100.0,
  exact_row_overlap: 12,
  privacy_summary: {
    exact_row_overlap: 12,
    direct_identifier_overlap: 8,
    singling_out_rate: 0.31,
    failed_gates: ['patients.exact_row_overlap', 'patients.direct_identifier_overlap'],
  },
  utility_summary: {
    mean_distribution_similarity: 0.91,
    failed_gates: [],
  },
  integrity_summary: {
    orphan_foreign_keys: 0,
    failed_gates: [],
  },
  completed_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
  publish_result: null,
  synthetic_urns: [
    'urn:li:dataset:(urn:li:dataPlatform:postgres,doppel.healthcare.patients_synthetic,NON_PROD)',
    'urn:li:dataset:(urn:li:dataPlatform:postgres,doppel.healthcare.encounters_synthetic,NON_PROD)',
  ],
};

const toast = (message, error = false) => {
  const node = $('#toast');
  node.textContent = message;
  node.className = `toast show${error ? ' error' : ''}`;
  window.setTimeout(() => node.className = 'toast', 3200);
};

const api = async (path, options = {}) => {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed: ${response.status}`);
  }
  if (response.status === 204) return null;
  return response.json();
};

const formatDate = (iso) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
};

const formatPercent = (value, digits = 1) => {
  const num = Number(value);
  if (Number.isNaN(num)) return '—';
  return `${(num * (num <= 1 ? 100 : 1)).toFixed(digits)}%`;
};

const getMetric = (report, predicate) => {
  if (!report?.tables) return null;
  for (const table of report.tables) {
    for (const metric of [...table.privacy_metrics, ...table.utility_metrics]) {
      if (predicate(metric)) return metric;
    }
  }
  return null;
};

const getDirectOverlap = (report) =>
  report?.privacy_summary?.direct_identifier_overlap ??
  report?.tables?.reduce((sum, t) => {
    const m = t.privacy_metrics.find((x) => x.name === 'direct_identifier_overlap');
    return sum + (m ? Number(m.value) : 0);
  }, 0) ??
  0;

const getSinglingOutRate = (report) =>
  report?.privacy_summary?.singling_out_rate ??
  Math.max(
    0,
    ...(report?.tables?.map((t) => {
      const m = t.privacy_metrics.find((x) => x.name === 'quasi_identifier_singling_out_rate');
      return m ? Number(m.value) : 0;
    }) || [0])
  );

const getCorrelationSimilarity = (report) => {
  const summary = report?.utility_summary;
  if (summary?.mean_distribution_similarity !== undefined && summary.metric_names) {
    const names = summary.metric_names;
    const scores = summary.distribution_scores || [];
    const values = scores.filter((_, i) => names[i] === 'correlation_similarity');
    if (values.length) return values[0];
  }
  const m = getMetric(report, (x) => x.name === 'correlation_similarity');
  return m ? Number(m.value) : null;
};

const getConditionalSimilarity = (report) => {
  const summary = report?.utility_summary;
  if (summary?.mean_distribution_similarity !== undefined && summary.metric_names) {
    const names = summary.metric_names;
    const scores = summary.distribution_scores || [];
    const values = scores.filter((_, i) => names[i].startsWith('conditional_mean:'));
    if (values.length) return values.reduce((a, b) => a + b, 0) / values.length;
  }
  const metrics = [];
  report?.tables?.forEach((t) => {
    t.utility_metrics.forEach((m) => {
      if (m.name.startsWith('conditional_mean:')) metrics.push(Number(m.value));
    });
  });
  return metrics.length ? metrics.reduce((a, b) => a + b, 0) / metrics.length : null;
};

const showScreen = (index) => {
  state.currentScreen = index;
  $$('.screen').forEach((screen, i) => screen.classList.toggle('active', i === index));
  $$('.nav-item').forEach((item, i) => {
    item.classList.toggle('active', i === index);
    item.classList.toggle('done', i < index);
  });
  const titles = [
    'Production healthcare data',
    'Generation plan',
    'Live pipeline',
    'Verification',
    'DataHub writeback',
  ];
  $('#pageTitle').textContent = titles[index];
};

const loadHealth = async () => {
  const health = await api('/api/health');
  $('#modeLabel').textContent = health.mode === 'datahub' ? 'Live DataHub' : 'Fixture mode';
};

const loadAsset = async () => {
  const asset = await api('/api/assets/healthcare');
  state.asset = asset;
  renderAssetScreen(asset);
  renderPlanScreen(asset);
};

const renderAssetScreen = (asset) => {
  $('#assetHeaderLine').textContent = `${asset.domain} · ${asset.owner}`;

  const patients = asset.tables.find((t) => t.name === 'patients');
  const encounters = asset.tables.find((t) => t.name === 'encounters');

  if (patients) {
    $('#patientsRowCount').textContent = asset.row_counts.patients.toLocaleString();
    $('#patientsTags').innerHTML = renderPills(patients.tags);
    $('#patientsFields').innerHTML = patients.columns.map(renderFieldRow).join('');
  }
  if (encounters) {
    $('#encountersRowCount').textContent = asset.row_counts.encounters.toLocaleString();
    $('#encountersTags').innerHTML = renderPills(encounters.tags);
    $('#encountersFields').innerHTML = encounters.columns.map(renderFieldRow).join('');
  }
};

const renderPills = (tags) =>
  tags
    .map((tag) => {
      const cls = tag.toUpperCase() === 'PII' ? 'pii' : tag.toUpperCase() === 'PHI' ? 'phi' : '';
      return `<span class="pill ${cls}">${tag}</span>`;
    })
    .join('');

const renderFieldRow = (column) => {
  const tags = column.tags
    .map((tag) => `<span class="${tag.toUpperCase() === 'PII' ? 'pii' : ''}">${tag}</span>`)
    .join(', ');
  return `
    <div class="field-row">
      <strong>${column.name}</strong>
      <span class="field-type">${column.semantic_type}</span>
      <span class="field-tags">${tags}</span>
    </div>`;
};

const renderPlanScreen = (asset) => {
  const panels = asset.tables
    .map((table) => {
      const rows = table.columns
        .map((column) => {
          const strategy = column.strategy || column.semantic_type;
          const isSensitive = column.tags.some((t) => ['PII', 'PHI'].includes(t.toUpperCase()));
          const dstClass = isSensitive ? 'dst warn' : 'dst';
          return `
            <div class="plan-row">
              <span class="src">${column.name}</span>
              <span class="arrow">→</span>
              <span class="${dstClass}">${strategy}</span>
            </div>`;
        })
        .join('');
      return `
        <div class="plan-table">
          <div class="plan-table-head">
            <span class="eyebrow">${table.name}</span>
            <h3>healthcare.${table.name}</h3>
          </div>
          ${rows}
        </div>`;
    })
    .join('');
  $('#planPanels').innerHTML = panels;
};

const resetPipeline = () => {
  $('#pipelineSubtitle').textContent = 'Connecting to backend…';
  $('#pipelineLog').innerHTML = '';
  $$('.pipeline-stages li').forEach((node) =>
    node.classList.remove('active', 'done', 'error')
  );
};

const logPipeline = (status, message) => {
  const log = $('#pipelineLog');
  const entry = document.createElement('div');
  entry.className = `log-entry ${status}`;
  entry.textContent = `[${status.toUpperCase()}] ${message}`;
  log.appendChild(entry);
  log.scrollTop = log.scrollHeight;
};

const setStageStatus = (stage, status) => {
  const node = $(`.pipeline-stages li[data-stage="${stage}"]`);
  if (!node) return;
  node.classList.remove('active', 'done', 'error');
  node.classList.add(status);
};

const startPipeline = async () => {
  showScreen(2);
  resetPipeline();
  $('#pipelineSubtitle').textContent = 'Streaming live stage events from the backend.';

  try {
    const response = await fetch('/api/runs/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(DEMO_CONFIG),
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `Pipeline failed: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = JSON.parse(line.slice(6));
        handleStreamEvent(payload);
      }
    }
  } catch (error) {
    logPipeline('error', error.message);
    toast(error.message, true);
  }
};

const handleStreamEvent = (payload) => {
  if (payload.type === 'stage') {
    const { stage, status, message } = payload;
    setStageStatus(stage, status);
    logPipeline(status, message);
    if (status === 'complete') {
      const previous = $(`.pipeline-stages li[data-stage="${stage}"]`);
      if (previous) previous.previousElementSibling?.classList.add('done');
    }
  } else if (payload.type === 'error') {
    logPipeline('error', payload.message);
    toast(payload.message, true);
  } else if (payload.type === 'complete') {
    if (payload.report) {
      state.run = payload.report;
      state.showingRejected = false;
      showScreen(3);
      renderVerification(payload.report);
    } else {
      toast('Pipeline completed without a report.', true);
    }
  }
};

const renderVerification = (report) => {
  const verdict = $('#verdict');
  verdict.classList.remove('verified', 'rejected');
  verdict.classList.add(report.decision === 'VERIFIED' ? 'verified' : 'rejected');
  $('#verdictStatus').textContent = report.decision;
  $('#verdictReason').textContent =
    report.decision === 'VERIFIED'
      ? 'All privacy and integrity gates passed; utility cleared the documented threshold.'
      : 'One or more required gates failed. Review the reasons below.';

  const directOverlap = getDirectOverlap(report);
  const singlingRate = getSinglingOutRate(report);
  const correlation = getCorrelationSimilarity(report);
  const conditional = getConditionalSimilarity(report);

  $('#metricOverlap').textContent = report.exact_row_overlap;
  $('#metricDirect').textContent = directOverlap;
  $('#metricPrivacy').textContent = formatPercent(report.privacy_score);
  $('#metricUtility').textContent = formatPercent(report.utility_score);
  $('#metricIntegrity').textContent = formatPercent(report.fk_integrity);
  $('#metricSingling').textContent = formatPercent(singlingRate);
  $('#metricCorrelation').textContent = correlation !== null ? formatPercent(correlation) : '—';
  $('#metricConditional').textContent = conditional !== null ? formatPercent(conditional) : '—';

  colorMetricCard('#metricOverlap', report.exact_row_overlap === 0);
  colorMetricCard('#metricDirect', directOverlap === 0);
  colorMetricCard('#metricPrivacy', report.privacy_score >= 95);
  colorMetricCard('#metricUtility', report.utility_score >= 70);
  colorMetricCard('#metricIntegrity', report.fk_integrity >= 95);
  colorMetricCard('#metricSingling', singlingRate <= 0.25, singlingRate <= 0.10);
  colorMetricCard('#metricCorrelation', correlation !== null && correlation >= 0.75, correlation !== null && correlation >= 0.90);
  colorMetricCard('#metricConditional', conditional !== null && conditional >= 0.75, conditional !== null && conditional >= 0.90);

  $('#reasonsPanel').innerHTML = `
    <h4>Decision reasons</h4>
    ${report.reasons
      .map((reason) => {
        const isFail = /below|failed|overlap|reproduced|orphan/i.test(reason);
        return `
          <div class="reason-row ${isFail ? 'fail' : 'pass'}">
            <b>${isFail ? '✕' : '✓'}</b>
            <span>${reason}</span>
          </div>`;
      })
      .join('')}`;

  $('#toWritebackButton').disabled = report.decision !== 'VERIFIED';
};

const colorMetricCard = (selector, pass, good = pass) => {
  const article = $(selector)?.closest('article');
  if (!article) return;
  article.classList.remove('good', 'warn', 'bad');
  if (pass && good) article.classList.add('good');
  else if (pass) article.classList.add('warn');
  else article.classList.add('bad');
};

const renderWriteback = () => {
  const report = state.run;
  if (!report) return;

  $('#expiryValue').textContent = formatDate(report.expires_at);
  $('#ownerDomainValue').textContent = state.asset
    ? `${state.asset.owner} · ${state.asset.domain}`
    : '—';

  const verifiedPill = $('#verifiedPill');
  if (report.decision === 'VERIFIED') {
    verifiedPill.textContent = 'DOPPEL_VERIFIED';
    verifiedPill.classList.remove('bad');
    verifiedPill.classList.add('good');
  } else {
    verifiedPill.textContent = 'DOPPEL_REJECTED';
    verifiedPill.classList.remove('good');
    verifiedPill.classList.add('bad');
  }

  const downloadUrl = `/api/runs/${report.run_id}/download`;
  $('#downloadTwinButton').href = downloadUrl;
  $('#downloadEvidenceButton').href = downloadUrl;
};

$('#startDemoButton').addEventListener('click', () => showScreen(1));
$('#backToAssetButton').addEventListener('click', () => showScreen(0));
$('#runPipelineButton').addEventListener('click', startPipeline);
$('#backToPipelineButton').addEventListener('click', () => showScreen(2));
$('#toWritebackButton').addEventListener('click', () => {
  renderWriteback();
  showScreen(4);
});
$('#restartButton').addEventListener('click', () => {
  state.run = null;
  state.showingRejected = false;
  showScreen(0);
});
$('#showRejectedButton').addEventListener('click', () => {
  state.showingRejected = true;
  renderVerification(REJECTED_EXAMPLE);
});
$('#refreshButton').addEventListener('click', async () => {
  await Promise.all([loadHealth(), loadAsset()]);
  toast('Workspace refreshed.');
});

Promise.all([loadHealth(), loadAsset()]).catch((error) => toast(error.message, true));
