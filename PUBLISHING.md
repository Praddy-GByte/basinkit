# Publishing basinkit

The order below is not arbitrary. **Zenodo only ingests releases created while
the integration is already switched on**. Enable it after you tag and that
release gets no DOI, and there is no backfill. The fix would be to bump the
version and cut another release, so it is worth getting right the first time.

Set this once and use it throughout:

```bash
export GH_USER="your-github-username"     # exactly as it appears in your profile URL
```

Then replace the placeholder in two files:

```bash
sed -i '' "s/Praddy-GByte/$GH_USER/g" CITATION.cff pyproject.toml   # macOS
sed -i     "s/Praddy-GByte/$GH_USER/g" CITATION.cff pyproject.toml   # Linux
```

---

## 1. Repository: 20 minutes

```bash
cd basinkit
git init -b main
git add .
git commit -m "basinkit 0.1.0"

gh auth login                              # browser, HTTPS, once
gh repo create basinkit --public --source=. --remote=origin --push \
  --description "Point to river basin to every open Earth observation layer. Global, no account required."

gh repo edit --add-topic hydrology --add-topic watershed --add-topic remote-sensing \
             --add-topic earth-observation --add-topic gis --add-topic qgis \
             --add-topic open-data --add-topic python --add-topic stac
```

No `gh`? Create the repo on github.com, then:

```bash
git remote add origin https://github.com/$GH_USER/basinkit.git
git push -u origin main
```

**Check before moving on:** `LICENSE`, `CITATION.cff` and
`.github/workflows/release.yml` are all visible on the repo page, and GitHub
shows a "Cite this repository" button on the right.

---

## 2. PyPI trusted publisher: 15 minutes

The workflow publishes over OIDC, so there is no API token to create or leak.
The project does not exist on PyPI yet, which is what a *pending* publisher is
for.

1. Create an account at `pypi.org` and enable 2FA; an authenticator app is enough.
2. Avatar → **Your account** → **Publishing** (`pypi.org/manage/account/publishing/`).
   It sits under your account rather than a project because the project does not
   exist yet.
3. On the **GitHub** tab, fill in exactly:

   | field | value |
   |---|---|
   | PyPI Project Name | `basinkit` |
   | Owner | your GitHub username |
   | Repository name | `basinkit` |
   | Workflow name | `release.yml` &nbsp;(**filename only**, not the full path) |
   | Environment name | `pypi` |

   The environment is mandatory here because `release.yml` declares
   `environment: pypi`. If the two disagree the upload fails with
   `invalid-pending-publisher`.

4. In the repo: **Settings → Environments → New environment**, name it `pypi`.
   Add yourself under **Required reviewers** so a release cannot publish without
   your click.

**A pending publisher does not reserve the name.** If someone registers
`basinkit` before your first upload, the pending publisher is invalidated. Do
not leave a long gap between this step and step 6.

---

## 3. Zenodo: 10 minutes, and it must come before the release

1. `zenodo.org` → **Log in with GitHub** → **Authorize zenodo**.
2. Profile menu → **GitHub** → **Sync now**.
3. Find `basinkit` in the list and **toggle it on**.
4. Refresh and confirm the toggle stayed on.

Zenodo can only see public repositories, and it needs a detectable `LICENSE` or
it will mark the record's licence unknown. Both are already true.

---

## 4. Fill in the links

The two reports and the README currently point at nothing. Now that the URLs
exist, put them in:

- `README.md`: repository, PyPI and DOI badges at the top
- `docs/verification.md`: the run-of-record line
- both published reports: the footer

---

## 5. Cut the release: 5 minutes

```bash
git add -A && git commit -m "Add citation metadata and publishing links"
git push

git tag v0.1.0
git push origin v0.1.0

gh release create v0.1.0 \
  --title "basinkit 0.1.0" \
  --notes-file RELEASE_NOTES.md
```

This does three things at once: the workflow builds and uploads to PyPI (pausing
for your approval on the `pypi` environment), Zenodo ingests the tarball and
mints a DOI, and GitHub shows the release.

Watch it: `gh run watch`.

---

## 6. Close the loop: 10 minutes

1. `pip install basinkit` in a clean virtualenv. If that fails, nothing else
   matters.
2. Copy the **version DOI** from the Zenodo record; cite the version, not the
   concept DOI, in papers.
3. Put it in `CITATION.cff`, commit, push.
4. Add the badges:

```markdown
[![PyPI](https://img.shields.io/pypi/v/basinkit)](https://pypi.org/project/basinkit/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
[![Tests](https://github.com/Praddy-GByte/basinkit/actions/workflows/ci.yml/badge.svg)](https://github.com/Praddy-GByte/basinkit/actions)
```

---

## Optional: hold the hyphenated name

PyPI treats `basinkit` and `basin-kit` as different names. Holding the second
costs one upload:

```bash
python -m pip install --upgrade build twine
# in a scratch folder with a minimal pyproject.toml naming the package basin-kit
python -m build && python -m twine upload dist/*
# username: __token__      password: the API token from pypi.org/manage/account/token/
```

PyPI's policy permits defensive registration where the names are genuinely
related; do not do this for names you have no claim to.

---

## Afterwards

**QGIS plugin**: `plugins.qgis.org` → register → **Share a plugin** → upload
`basinkit_qgis-0.1.0.zip`. Reviewers check the metadata, the licence and that it
loads. The plugin repository is a discovery channel that keeps working long
after a launch post has scrolled away.

**JOSS**: needs the public repository, documentation, a test suite and an
archived DOI, all of which now exist, plus a short `paper.md`. Review is public
and typically runs six to twelve weeks.
