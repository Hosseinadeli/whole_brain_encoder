from tqdm import tqdm
import numpy as np
from pathlib import Path
from scipy.stats import pearsonr as corr
import cortex
import cortex.polyutils
import matplotlib.pyplot as plt
import sys
import contextlib
from io import StringIO
import copy
import argparse
from utils.args import get_args_parser, get_model_dir_args, get_run_dir


# Function to suppress print statements
@contextlib.contextmanager
def suppress_print():
    # Redirect stdout to suppress printing
    original_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        yield
    finally:
        # Restore original stdout after suppression
        sys.stdout = original_stdout


def plot_parcels(lh, rh, title="", fig_path=None, cmap="RdBu_r", clip=1):
    # =============================================================================
    # Plot parameters for colorbar
    # =============================================================================
    plt.rc("xtick", labelsize=19)
    plt.rc("ytick", labelsize=19)

    # =============================================================================
    # Plot the results on brain surfaces
    # =============================================================================
    subject = "fsaverage"
    data = np.append(lh, rh)
    vertex_data = cortex.Vertex(data, subject, cmap=cmap, vmin=0, vmax=clip)  # "afmhot"

    # cmap = plt.cm.get_cmap("Oranges").copy()
    # cmap.set_bad(color="lightgrey")
    # vertex_data = cortex.Vertex(data, subject, cmap=cmap, vmin=0, vmax=1)
    with suppress_print():
        cortex.quickshow(vertex_data)  # , with_curvature=True)

    plt.title(title)

    if fig_path is not None:
        plt.savefig(fig_path, dpi=300)
    else:
        plt.show()


def plot_run_results(args, avg_or_nonavg):
    val_correlations = {}

    for hemi in ["lh", "rh"]:
        val_correlation = np.zeros(163842)

        for axis in ["posterior", "anterior"]:
            args.hemi = hemi
            args.axis = axis
            model_dir = Path(get_model_dir_args(args))

            val_corr = np.load(
                model_dir / f"{hemi}_{args.split}_corr_{avg_or_nonavg}.npy"
            )
            val_corr = np.nan_to_num(val_corr)

            val_correlation += val_corr

        val_correlations[hemi] = val_correlation

    run_dir = get_run_dir(args)

    for clip_value in [0.3, 1]:
        plot_parcels(
            val_correlations["lh"],
            val_correlations["rh"],
            title=f"Sub: {args.subj} Transformer ({avg_or_nonavg} data) {args.split} Correlation, clip={clip_value}",
            fig_path=run_dir
            / f"transformer_{args.split}_correlation_{avg_or_nonavg}_clip{str(clip_value).replace('.', '')}.jpg",
            cmap="RdBu_r",
            clip=clip_value,
        )

    mean_coors = {key: value.mean() for key, value in val_correlations.items()}

    plt_title = f"sub{args.subj} enc_{args.enc_output_layer} run_{args.run} ({avg_or_nonavg} data) ROI Correlation"

    plot_roi_correlation(
        plt_title, args.subj, val_correlations, avg_or_nonavg, run_dir, args.split
    )

    # with open(run_dir, "a") as f:
    #     f.write(f"avg correlation: {mean_coors}\n")


def plot_roi_correlation(
    plt_title, subj, val_correlations, avg_or_nonavg, save_dir, split
):
    neural_data_path = Path(
        "/engram/nklab/datasets/natural_scene_dataset/model_training_datasets/neural_data"
    )
    metadata = np.load(
        neural_data_path / f"metadata_sub-{int(subj):02}.npy", allow_pickle=True
    ).item()

    challenge_cover = np.zeros(
        len(metadata["lh_anterior_vertices"]) + len(metadata["rh_anterior_vertices"]),
        dtype=bool,
    )
    roi_corr = {"lh": {}, "rh": {}}
    for hemi in ["lh", "rh"]:
        for roi, vertices in metadata[f"{hemi}_rois"].items():
            roi_corr[hemi][roi] = val_correlations[hemi][vertices].mean()
            challenge_cover |= vertices
        roi_corr[hemi]["All vertices"] = val_correlations[hemi][challenge_cover].mean()

    x = np.arange(len((roi_corr["lh"].keys())))
    width = 0.35
    fig, ax = plt.subplots(figsize=(12, 6))
    for hemi, pos in zip(["lh", "rh"], [x - width / 2, x + width / 2]):
        values = [roi_corr[hemi][key] for key in roi_corr[hemi].keys()]
        bars = ax.bar(
            pos,
            values,
            width,
            label=hemi,
        )
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,  # X position (center of the bar)
                bar.get_height() + 0.05,  # Y position (top of the bar)
                f"{value:.2f}",  # Text (formatted value)
                ha="center",
                va="bottom",
                fontsize=6,  # Alignment and size
            )
    ax.set_ylabel("Mean Pearson's r")
    ax.set_xticks(x)
    ax.set_xticklabels(list(roi_corr["lh"].keys()), rotation=90, ha="center")
    ax.legend()

    # Optional: Set y-axis limit
    ax.set_ylim(0, 1)  # Adjust based on your data range

    plt.tight_layout()
    plt.title(plt_title)
    plt.savefig(save_dir / f"{split}_roi_correlation_{avg_or_nonavg}.jpg", dpi=300)


def main():
    parser = argparse.ArgumentParser(
        "model training and evaluation script", parents=[get_args_parser()]
    )
    parser.add_argument("--ensemble", type=bool, default=False)
    parser.add_argument("--ensemble_dir", type=str, default="enc_1_5_run_1_5")
    parser.add_argument("--split", type=str, default="val")
    args = parser.parse_args()

    if args.ensemble:
        results_dir = (
            Path("/engram/nklab/algonauts/ethan/transformer_brain_encoder/results")
            / args.ensemble_dir
        )
        val_correlations = {}
        val_correlations["lh"] = np.load(results_dir / f"lh_{args.split}_corr_avg.npy")
        val_correlations["rh"] = np.load(results_dir / f"rh_{args.split}_corr_avg.npy")

        for clip_value in [0.3, 1]:
            plot_parcels(
                val_correlations["lh"],
                val_correlations["rh"],
                title=f"Sub: {args.subj} Transformer (avg data) {args.split} Correlation, clip={clip_value}",
                fig_path=results_dir
                / f"emsemble_{args.split}_correlation_avg_clip{str(clip_value).replace('.', '')}.jpg",
                cmap="RdBu_r",
                clip=clip_value,
            )

        plot_roi_correlation(
            f"sub{args.subj} enc_{args.enc_output_layer} run_{args.run} Emsemble (avg data) ROI Correlation",
            args.subj,
            val_correlations,
            "avg",
            results_dir,
            args.split,
        )

        return
    plot_run_results(args, "nonavg")
    plot_run_results(args, "avg")

    # expl_var = {}

    # val_correlations_nc_corrected = copy.deepcopy(val_correlations)
    # for hemi in ["lh", "rh"]:
    #     nc = metadata[f"{hemi}_ncsnr"].squeeze()

    #     print("hemi:", hemi, "avg noise ceiling:", nc.mean())
    #     with open(run_dir, "a") as f:
    #         f.write(f"hemi: {hemi}, avg noise ceiling: {nc.mean()}\n")

    #     val_correlations_nc_corrected[hemi][val_correlations_nc_corrected[hemi] < 0] = 0
    #     val_correlations_nc_corrected[hemi] = val_correlations_nc_corrected[hemi] ** 2

    #     nc[nc == 0] = 1e-14

    #     # # Compute the noise-ceiling-normalized encoding accuracy
    #     expl_var[hemi] = np.divide(val_correlations_nc_corrected[hemi], nc)

    #     # # Set the noise-ceiling-normalized encoding accuracy to 1 for those vertices
    #     # # in which the r2 scores are higher than the noise ceiling, to prevent
    #     # # encoding accuracy values higher than 100%
    #     expl_var[hemi][expl_var[hemi] > 1] = 1

    # print(
    #     f"[averaged explained variance] lh: {expl_var['lh'].mean()}, rh: {expl_var['rh'].mean()}"
    # )
    # with open(run_dir, "a") as f:
    #     f.write(
    #         f"[averaged explained variance] lh: {expl_var['lh'].mean()}, rh: {expl_var['rh'].mean()}"
    #     )

    # for clip_val in [0.3, 1]:
    #     plot_parcels(
    #         expl_var["lh"],
    #         expl_var["rh"],
    #         title=f"Sub: {args.subj} Transformer (nonaveraged data) Validation Correlation, Noise Ceiling Normalized, clip={clip_val}",
    #         fig_path=model_dir
    #         / f"transformer_validation_explvar_{str(clip_val).replace('.', '')}.png",
    #         clip=clip_val,
    #     )


if __name__ == "__main__":
    main()