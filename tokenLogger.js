const { Client } = require('@notionhq/client');

const PRICING = {
  'claude-sonnet-4-6': { input: 3.00, output: 15.00, cacheRead: 0.30, cacheCreate: 3.75 },
  'claude-opus-4-6':   { input: 15.00, output: 75.00, cacheRead: 1.50, cacheCreate: 18.75 },
  'claude-haiku-4-5-20251001': { input: 0.80, output: 4.00, cacheRead: 0.08, cacheCreate: 1.00 },
};

function estimateCost({ model, inputTokens, outputTokens, cacheReadTokens, cacheCreationTokens }) {
  const p = PRICING[model] || PRICING['claude-sonnet-4-6'];
  const M = 1_000_000;
  return (inputTokens/M)*p.input + (outputTokens/M)*p.output + (cacheReadTokens/M)*p.cacheRead + (cacheCreationTokens/M)*p.cacheCreate;
}

function createLogger(notionClient) {
  const TOKEN_LOG_DB = process.env.TOKEN_LOG_DB_ID || null;

  async function logSession({ sesjonId, kundeNavn, jobbtype, skillVersjon, model, inputTokens, outputTokens, cacheReadTokens, cacheCreationTokens, toolCalls, notat }) {
    if (!TOKEN_LOG_DB) return { logged: false, reason: 'no TOKEN_LOG_DB_ID' };
    const kostnad = estimateCost({ model, inputTokens, outputTokens, cacheReadTokens, cacheCreationTokens });
    const dato = new Date().toISOString().slice(0, 10);
    try {
      const page = await notionClient.pages.create({
        parent: { database_id: TOKEN_LOG_DB },
        properties: {
          'Sesjon ID':             { title: [{ text: { content: sesjonId || `${dato}-${jobbtype||'ukjent'}` } }] },
          'Dato':                  { date: { start: dato } },
          'Kunde':                 { rich_text: [{ text: { content: kundeNavn || '' } }] },
          'Jobbtype':              { rich_text: [{ text: { content: jobbtype || '' } }] },
          'SKILL versjon':         { select: { name: skillVersjon || 'ukjent' } },
          'Modell':                { select: { name: model || 'claude-sonnet-4-6' } },
          'Input tokens':          { number: inputTokens || 0 },
          'Output tokens':         { number: outputTokens || 0 },
          'Cache read tokens':     { number: cacheReadTokens || 0 },
          'Cache creation tokens': { number: cacheCreationTokens || 0 },
          'Tool calls':            { number: toolCalls || 0 },
          'Est. kostnad USD':      { number: Math.round(kostnad * 10000) / 10000 },
          'Notat':                 { rich_text: [{ text: { content: notat || '' } }] },
        }
      });
      console.log(`[tokenLogger] ${sesjonId} → $${kostnad.toFixed(4)}`);
      return { logged: true, notionId: page.id, kostnad };
    } catch (err) {
      console.error('[tokenLogger] Feil:', err.message);
      return { logged: false, error: err.message };
    }
  }

  async function getStats() {
    if (!TOKEN_LOG_DB) return { error: 'TOKEN_LOG_DB_ID ikke satt' };
    try {
      const response = await notionClient.databases.query({ database_id: TOKEN_LOG_DB, page_size: 100, sorts: [{ property: 'Dato', direction: 'descending' }] });
      const rows = response.results.map(p => ({
        sesjonId:            p.properties['Sesjon ID']?.title?.[0]?.plain_text || '',
        dato:                p.properties['Dato']?.date?.start || '',
        jobbtype:            p.properties['Jobbtype']?.rich_text?.[0]?.plain_text || '',
        skillVersjon:        p.properties['SKILL versjon']?.select?.name || '',
        modell:              p.properties['Modell']?.select?.name || '',
        inputTokens:         p.properties['Input tokens']?.number || 0,
        cacheReadTokens:     p.properties['Cache read tokens']?.number || 0,
        cacheCreationTokens: p.properties['Cache creation tokens']?.number || 0,
        toolCalls:           p.properties['Tool calls']?.number || 0,
        kostnad:             p.properties['Est. kostnad USD']?.number || 0,
      }));
      const byVersjon = {};
      for (const r of rows) {
        const v = r.skillVersjon || 'ukjent';
        if (!byVersjon[v]) byVersjon[v] = [];
        byVersjon[v].push(r);
      }
      const summary = {};
      for (const [versjon, s] of Object.entries(byVersjon)) {
        const n = s.length;
        const avg = arr => arr.reduce((a,b)=>a+b,0)/n;
        summary[versjon] = {
          antallSesjoner: n,
          snittKostnad:    Math.round(avg(s.map(x=>x.kostnad))*10000)/10000,
          maksKostnad:     Math.max(...s.map(x=>x.kostnad)),
          snittCacheCreate:  Math.round(avg(s.map(x=>x.cacheCreationTokens))),
          snittToolCalls:    Math.round(avg(s.map(x=>x.toolCalls))*10)/10,
          totalKostnad:      Math.round(s.reduce((a,x)=>a+x.kostnad,0)*100)/100,
        };
      }
      const baseline = { antallSesjoner: 23, snittKostnad: 5.49, maksKostnad: 20.30, snittCacheCreate: 527319, kilde: 'AI-playground proxy feb–apr 2026' };
      return { baseline, versjoner: summary, sesjoner: rows, hentet: new Date().toISOString() };
    } catch (err) {
      return { error: err.message };
    }
  }

  return { logSession, getStats };
}

module.exports = { createLogger, estimateCost };
