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
- [ ] Run bandit and safety
- [ ] Build docker images and make sure runnable unit tests pass
        - docker build . -t talkpipe:experimental
- [ ] Tag repository
- [ ] Build whl files
- [ ] Install whl file in new environment and test a script in chatterlang_workbench
- [ ] Run examples in the tutorials
- [ ] Push code to repo
- [ ] Push tags to repo
- [ ] Make sure everything passes on github
- [ ] Create a release on github
