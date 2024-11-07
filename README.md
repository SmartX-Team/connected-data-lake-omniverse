# Connected Data Lake - NVIDIA Omniverse Extensions

## Getting Started

### Requirements

- bash
- busybox
- curl
- findutils
- [Just `cargo install just`](https://github.com/casey/just)
- [Rust (rustup)](https://rustup.rs/)

#### Ubuntu 24.04 or Above

```bash
# Install the dependencies
sudo apt-get update && sudo apt-get install -y \
  bash \
  busybox \
  curl \
  findutils \
  just \
  rustup

# Install the latest stable cargo & rustc (>=1.82)
rustup default stable
```

#### Windows 11 or Above

```bash
# Install the dependencies
winget install -e --id Git.Git  # git (bash, curl, findutils)
winget install -e --id frippery.busybox-w32  # busybox
winget install -e --id Casey.Just  # just
winget install -e --id Rustlang.Rustup  # rustup

# Install the latest stable cargo & rustc (>=1.82)
rustup default stable
```

### One-shot Command Line

On your bash shell, type below:

```bash
just run editor.base
```

## LICENSE

Please check our [LICENSE file](/LICENSE).
