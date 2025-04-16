---
name: Release Checklist
about: Steps for doing a new release
title: Release vX.Y.Z
labels: ''
assignees: ''

---

- [ ] Update CHANGELOG
- [ ] Commit all changes
- [ ] Ensure unit tests pass in live environment
- [ ] Merge into master
- [ ] Build docker image
- [ ] Tag repository
- [ ] Build whl files
- [ ] Install whl file in new environment and test a script in chatterlang_server
- [ ] Push to pypi
- [ ] Push code to repo
- [ ] Push tags to repo
