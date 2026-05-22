# How to Contribute

Thanks for helping. Keep it simple.

## Before You Push

Install Git LFS once. We use it for CAD, STL, STEP, PCB, video, PDF.

```
brew install git-lfs       # macOS
sudo apt install git-lfs   # Linux
git lfs install
```

Then `git add` and `git commit` work normally. See `docs/git-lfs.md`.

## Upload CAD

- Put editable files in `cad/source/` (keep the original format: .f3d, .FCStd, .SLDPRT, etc.)
- Always export and upload a `.step` to `cad/step/` so anyone can open it
- Export `.stl` to `cad/stl/` for 3D printing
- One folder per part if it has many versions

File name format: `part-name_v1.step`, `part-name_v2.step`

## Upload Electronics

- Schematics: PDF + source file (KiCad preferred)
- PCB: include Gerber zip for fab
- Update `electronics/bom/parts.csv` if you change parts

## Write Assembly Guide

- Use `assembly/README.md`
- Numbered steps. One photo per step.
- Photos in `assembly/photos/`, name them `step-01.jpg`, `step-02.jpg`...

## Rules

- No big words. Write so a beginner can follow.
- Test before you push. If you can, print or build it yourself first.
- Commit message: short, clear. Example: `add v2 leg bracket STEP file`
- One topic per Pull Request.

## License of Your Contributions

By sending a Pull Request you agree your contribution is licensed under the
same terms as the project:
- Hardware/CAD/docs: CC BY-NC-SA 4.0
- Code/firmware: PolyForm Noncommercial 1.0.0

This means your contribution is free for personal/community use and not for
commercial use without permission. See [LICENSE.md](LICENSE.md) for the summary
or [LICENSE](LICENSE) / [LICENSE-CODE](LICENSE-CODE) for full legal text.

## Issues

Open an Issue if:
- A file is missing or broken
- Instructions don't work
- You want to suggest a feature
- You found a bug

Use the templates in `.github/ISSUE_TEMPLATE/`.
