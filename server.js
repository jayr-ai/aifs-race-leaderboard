const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 3000;
const read = (p) => fs.readFileSync(path.join(__dirname, p), 'utf8');

const PAGES = { '/': 'index.html' };

const server = http.createServer((req, res) => {
  const url = req.url.split('?')[0];

  if (url === '/healthz') {
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('ok');
    return;
  }

  if (url === '/leaderboard.json') {
    try {
      res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-cache' });
      res.end(read('leaderboard.json'));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: String(e) }));
    }
    return;
  }

  if (url === '/status.json') {
    try {
      const d = JSON.parse(read('leaderboard.json'));
      const m = (d.periods && d.periods.monthly) || {};
      const leader = (m.reps && m.reps[0] && m.reps[0].name) || '';
      res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-cache' });
      res.end(JSON.stringify({
        asOf: d.asOf, teamCash: m.team && m.team.cash,
        dealsWon: m.team && m.team.dealsWon, leader
      }));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: String(e) }));
    }
    return;
  }

  const file = PAGES[url];
  if (file) {
    try {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-cache' });
      res.end(read(file));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'text/plain' });
      res.end('error');
    }
    return;
  }

  res.writeHead(302, { Location: '/' });
  res.end();
});

server.listen(PORT, () => {
  console.log('AIFS Sales Leaderboard on ' + PORT);
});
