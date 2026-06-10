import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = process.env.PORT || 3000;
const API_BASE = process.env.API_URL || 'http://localhost:4000';

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(express.static(path.join(__dirname, 'public')));
app.use(express.json());

const base = { apiBase: API_BASE };

app.get('/login', (req, res) => res.render('login', base));
app.get('/register', (req, res) => res.render('register', base));
app.get('/', (req, res) => res.render('landing', base));
app.get('/dashboard', (req, res) => res.render('dashboard', { ...base, page: 'dashboard' }));
app.get('/performance', (req, res) => res.render('performance', { ...base, page: 'performance' }));
app.get('/tasks', (req, res) => res.render('tasks', { ...base, page: 'tasks' }));
app.get('/tasks/:id', (req, res) => res.render('task-detail', { ...base, page: 'tasks', taskId: req.params.id }));
app.get('/meetings', (req, res) => res.render('meetings', { ...base, page: 'meetings' }));
app.get('/approvals', (req, res) => res.render('approvals', { ...base, page: 'approvals' }));
app.get('/employees', (req, res) => res.render('employees', { ...base, page: 'employees' }));
app.get('/audit-logs', (req, res) => res.render('audit-logs', { ...base, page: 'audit-logs' }));
app.get('/agent-configs', (req, res) => res.render('agent-configs', { ...base, page: 'agent-configs' }));

app.listen(PORT, () => {
  console.log(`AWOM  →  http://localhost:${PORT}`);
  console.log(`API   →  ${API_BASE}`);
});
