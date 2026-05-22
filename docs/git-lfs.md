# Git LFS — How To Use

This repo uses **Git LFS** for big binary files (CAD, STL, STEP, PCB, video, PDF, etc).
Small files (PNG, JPG, code, text) stay in regular git.

## First Time Setup

You need to install Git LFS once on your machine.

### macOS
```
brew install git-lfs
git lfs install
```

### Linux
```
sudo apt install git-lfs       # Debian / Ubuntu
sudo dnf install git-lfs       # Fedora
git lfs install
```

### Windows
Download from https://git-lfs.com — then:
```
git lfs install
```

## Clone the Repo

After LFS is installed, just clone normally. LFS files download automatically.

```
git clone https://github.com/autonomous-ai/autonomous-smart-desk-pro.git
```

If you already cloned before installing LFS, run:
```
cd autonomous-smart-desk-pro
git lfs install
git lfs pull
```

## Push New Big Files

Just `git add` and `git commit` like normal. LFS handles the rest.

```
git add cad/step/desk-frame_v1.step
git commit -m "add desk frame v1 step"
git push
```

The file types LFS tracks are in `.gitattributes`. If you add a new file type
that should be in LFS, run:

```
git lfs track "*.your-extension"
git add .gitattributes
git commit -m "lfs: track *.your-extension"
```

## File Types in LFS

CAD: `.step .stp .stl .f3d .f3z .FCStd .SLDPRT .SLDASM .SLDDRW .iges .igs .x_t .x_b .3mf .obj .dxf .dwg`
PCB: `.kicad_pcb .kicad_sch .kicad_pro .gbr .drl`
Archives: `.zip .tar.gz .7z .rar`
Video: `.mp4 .mov .mkv .webm`
Graphics: `.gif .psd .ai .eps`
3D scene: `.blend .fbx .glb .gltf`
Docs: `.pdf`

Small images (`.png`, `.jpg`) are kept in regular git so they show inline on GitHub.

## Check What's in LFS

```
git lfs ls-files
```

## Limits

GitHub free tier: 1 GB storage + 1 GB bandwidth/month per repo.
If we hit the limit we'll add a data pack or move large videos to YouTube and
just keep links in `assembly/videos/links.md`.
