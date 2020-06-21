from bulkvis.core import (
    concat_files_to_df,
    fuse_reads,
    length_stats,
    human_readable_yield,
    top_n,
)
from collections import OrderedDict
import pandas as pd
import numpy as np

_help = "Find incorrectly split reads from ONT sequencing_summary.txt and minimap2 .paf files"
_cli = (
    (
        "-d",
        "--distance",
        dict(
            help="Specify the maximum distance between consecutive mappings. This is the difference "
            "between 'Target Start' and 'Target End' in the paf file ",
            type=int,
            default=10000,
            metavar="",
        ),
    ),
    (
        "-t",
        "--top",
        dict(
            help="Show top N reads, by length, for the original dataset, fused reads, and "
            "corrected dataset",
            # This could be written better
            type=int,
            default=10,
            metavar="",
        ),
    ),
    # The behaviour of 'alt' is confusing... it seems like a double negative
    (
        "-a",
        "--alt",
        dict(
            help="""Exclude alternate assemblies""", action="store_false", default=True
        ),
    ),
    (
        "-s",
        "--summary",
        dict(
            metavar="",
            required=True,
            nargs="+",
            help="Sequencing summary file(s) generated by albacore or guppy. Can be compressed "
            "using gzip, bzip2, xz, or zip",
        ),
    ),
    (
        "-p",
        "--paf",
        dict(
            metavar="",
            required=True,
            nargs="+",
            help="paf file(s) generated by minimap2. Can be compressed using gzip, bzip2, "
            "xz, or zip",
        ),
    ),
    (
        "-o",
        "--output",
        dict(
            help="Specify name for the output file. This file only contains chains of reads.",
            default="fused_reads.txt",
            metavar="output",
        ),
    ),
)


def run(parser, args):
    """Input and output controller for bulkvis fuse"""
    # Open sequencing_summary_*.txt files into a single pd.DataFrame
    seq_sum_df = concat_files_to_df(
        file_list=args.summary,
        sep="\t",
        usecols=[
            "channel",
            "start_time",
            "duration",
            "run_id",
            "read_id",
            "sequence_length_template",
            "filename",
        ],
    )
    # Open minimap2 paf files into a single pd.DataFrame
    paf_df = concat_files_to_df(
        file_list=args.paf,
        sep="\t",
        header=None,
        usecols=[0, 4, 5, 7, 8],
        names=["Qname", "Strand", "Tname", "Tstart", "Tend"],
        engine="python",
    )
    fused_df, un_fused_df, to_be_fused_df = fuse_reads(
        seq_sum_df, paf_df, distance=args.distance, alt=args.alt
    )
    # Get yield numbers
    original_bases = np.sum(seq_sum_df["sequence_length_template"])
    new_lengths = pd.concat(
        [un_fused_df["sequence_length_template"], fused_df["combined_length"]]
    )
    new_bases = np.sum(new_lengths)
    seq_sum_lengths = seq_sum_df[seq_sum_df["sequence_length_template"] != 0][
        "sequence_length_template"
    ]
    # Initialize dictionary for holding metrics
    stats = OrderedDict()
    stats["Original reads:"] = length_stats(seq_sum_lengths)
    stats["Un-fused reads:"] = length_stats(un_fused_df["sequence_length_template"])
    stats["To be fused reads:"] = length_stats(
        to_be_fused_df["sequence_length_template"]
    )
    stats["Fused reads:"] = length_stats(fused_df["combined_length"])
    stats["New reads:"] = length_stats(new_lengths)
    # Convert stats dict to pandas.DataFrame for easy display
    stats_df = pd.DataFrame(stats).T[["COUNT", "MIN", "MAX", "MEAN", "N50"]]
    print(stats_df)
    # TODO: display yield better
    print(
        "\nTotal yield {y} ({b:,} bases)".format(
            y=human_readable_yield(original_bases), b=original_bases
        )
    )
    print(
        "Total yield {y} ({b:,} bases)\n".format(
            y=human_readable_yield(new_bases), b=new_bases
        )
    )
    top = abs(args.top)
    if top > 0:
        print("Top {n} original reads by length:".format(n=top))
        top_n(seq_sum_df, "sequence_length_template", top)
        print("Top {n} fused reads by combined length:".format(n=top))
        top_n(fused_df, "combined_length", top)
        print("Top {n} reads after correction:".format(n=top))
        top_n(pd.DataFrame(data={"length": new_lengths}), "length", top)
    header = [
        "coords",
        "run_id",
        "channel",
        "start_time",
        "duration",
        "combined_length",
        "target_name",
        "strand",
        "start_match",
        "end_match",
        "cat_read_id",
        "count",
    ]
    fused_df.to_csv(args.output, sep="\t", header=True, columns=header, index=False)
    print("Fused read summary file saved as {f}".format(f=args.output))
