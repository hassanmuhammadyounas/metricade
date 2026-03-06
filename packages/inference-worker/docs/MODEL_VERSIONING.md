# Model Versioning & Hot-Swap

## How to swap model weights without dropping messages

1. Train new model, export weights: `torch.save(model.state_dict(), "models/v2_simclr.pt")`
2. Update `MODEL_PATH` in `fly.toml` to point to new file
3. Add new weights file to the Docker image (rebuild)
4. Deploy with `fly deploy` — rolling deploy, subscriber stays alive during image pull
5. Old worker ACKs in-flight messages → new worker picks up from where it left off
6. Re-encode historical sessions manually if needed (run `src/main.py` in replay mode)

## Version naming convention

`v{N}_{training_method}.pt` — e.g. `v1_simclr_trained.pt`, `v2_simclr_finetuned.pt`

## Bootstrap phase

Before SimCLR training completes, `bootstrap_random.pt` produces vectors that are not semantically meaningful. Clustering will not produce useful labels during this phase. This is expected — the pipeline is operational, collecting data, and building the training corpus.
