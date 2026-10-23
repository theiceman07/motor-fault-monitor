# Branching and submission rules (agreed with the mentor)
- One shared repo, teammates added as collaborators (GitHub: Settings -> Collaborators).
- `main`: shared work only (shared code, shared milestones, docs everyone agrees on). Change it through pull requests, not force-pushes.
- Individual submissions: each student works on their own branch `ind/<your-name>` in this same repo.
  Evidence for any individually assessed milestone (your screenshots, your measurements, your commits) is committed there, from your own GitHub account.
  At least one commit per milestone M1..M5, with the milestone in the message (e.g. "M2: INT8 benchmark on Pi").
- Paste the link to YOUR branch (not `main`) in your own row of the assessment sheet.
- Never commit another student's results on your branch, and never rewrite history on a branch that holds submitted evidence.
- Do not commit secrets (`certs/`, `passwd`, `*.key`, `.env`).
- Ask your coach which rows count as shared and which as individual; when unsure, treat the row as individual.

```bash
git clone https://github.com/theiceman07/<repo>.git && cd <repo>
git config user.name "<your name>" && git config user.email "<your github email>"
git checkout -b ind/<your-name>
git push -u origin ind/<your-name>
```
