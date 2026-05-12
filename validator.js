const express = require('express');
const { Client } = require('@notionhq/client');
const { createLogger } = require('./tokenLogger');

const app = express();
app.use(express.json());

const notion = new Client({ auth: process.env.NOTION_TOKEN });
const { logSession, getStats } = createLogger(notion);
const MENGDETABELLER_DB = '180e0d6b-d285-4232-89d7-dbcc07ea8987';

app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'dgn-validator', version: '2.0.0' });
});

app.get('/mengder', async (req, res) => {
  const { jobbtype, materialtype } = req.query;
  if (!jobbtype) return res.status(400).json({ error: 'jobbtype required' });
  try {
    const response = await notion.databases.query({
      database_id: MENGDETABELLER_DB,
      filter: { property: 'Jobbtype', select: { equals: jobbtype } },
      page_size: 100,
    });
    const rows = response.results
      .map(p => ({
        aktivitet:    p.properties['Aktivitet']?.title?.[0]?.plain_text || '',
        enhet:        p.properties['Enhet']?.select?.name || '',
        ratio:        p.properties['Mengde pr m2']?.number ?? null,
        kategori:     p.properties['Kategori']?.select?.name || '',
        gjelder:      p.properties['Gjelder']?.select?.name || 'Felles',
        materialtype: p.properties['Materialtype']?.rich_text?.[0]?.plain_text || '',
        skalerbar:    p.properties['Skalerbar']?.checkbox ?? true,
      }))
      .filter(row => {
        if (!row.aktivitet) return false;
        if (row.gjelder === 'Felles') return true;
        if (!materialtype) return true;
        const mt = materialtype.toLowerCase();
        return row.materialtype.toLowerCase().includes(mt) || mt.includes(row.materialtype.toLowerCase());
      })
      .sort((a, b) => (a.gjelder !== 'Felles' ? 0 : 1) - (b.gjelder !== 'Felles' ? 0 : 1));
    res.json({ source: 'notion', jobbtype, materialtype: materialtype || null, count: rows.length, rows });
  } catch (err) {
    res.status(500).json({ source: 'error', error: err.message, rows: [] });
  }
});

app.post('/log-session', async (req, res) => {
  const { sesjonId, kundeNavn, jobbtype, skillVersjon, model, inputTokens, outputTokens, cacheReadTokens, cacheCreationTokens, toolCalls, notat } = req.body;
  if (!skillVersjon) return res.status(400).json({ error: 'skillVersjon er påkrevd' });
  const result = await logSession({ sesjonId, kundeNavn, jobbtype, skillVersjon, model: model||'claude-sonnet-4-6', inputTokens:inputTokens||0, outputTokens:outputTokens||0, cacheReadTokens:cacheReadTokens||0, cacheCreationTokens:cacheCreationTokens||0, toolCalls:toolCalls||0, notat });
  if (result.logged) res.json({ ok: true, notionId: result.notionId, kostnad: result.kostnad });
  else res.status(500).json({ ok: false, error: result.error || result.reason });
});

app.get('/stats', async (req, res) => {
  res.json(await getStats());
});

app.get('/stats/sammenlign', async (req, res) => {
  const stats = await getStats();
  if (stats.error) return res.status(500).json(stats);
  const { baseline, versjoner } = stats;
  const versjonsnavn = Object.keys(versjoner);
  if (!versjonsnavn.length) return res.json({ melding: 'Ingen loggede sesjoner ennå — POST til /log-session', baseline });
  const sisteVersjon = versjonsnavn[versjonsnavn.length - 1];
  const v = versjoner[sisteVersjon];
  res.json({
    versjon: sisteVersjon,
    antallSesjoner: v.antallSesjoner,
    kostnad: { baseline: baseline.snittKostnad, versjon: v.snittKostnad, deltaPct: Math.round(((v.snittKostnad-baseline.snittKostnad)/baseline.snittKostnad)*1000)/10, status: v.snittKostnad < baseline.snittKostnad ? '✓ BEDRE' : '✗ DÅRLIGERE' },
    cacheCreate: { baseline: baseline.snittCacheCreate, versjon: v.snittCacheCreate, deltaPct: Math.round(((v.snittCacheCreate-baseline.snittCacheCreate)/baseline.snittCacheCreate)*1000)/10, status: v.snittCacheCreate < baseline.snittCacheCreate ? '✓ BEDRE' : '✗ DÅRLIGERE' },
    toolCalls: { mal: 15, versjon: v.snittToolCalls, status: v.snittToolCalls !== null ? (v.snittToolCalls < 15 ? '✓ INNENFOR MÅL' : '✗ OVER MÅL') : '? IKKE MÅLT' },
  });
});

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => console.log(`DGN Validator v2.0 · Port ${PORT}`));
