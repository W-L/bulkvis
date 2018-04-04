from argparse import ArgumentParser
from collections import OrderedDict
import numpy as np
import pandas as pd


def main():
    args = get_args()
    # Open sequencing summary file
    sequencing_summary = args.summary
    ss_fields = ['channel', 'start_time', 'duration', 'run_id', 'read_id', 'sequence_length_template', 'filename']
    ss = pd.read_csv(sequencing_summary, sep='\t', usecols=ss_fields)
    ss = ss.sort_values(by=['channel', 'run_id', 'start_time'])
    ss['diff'] = ss['start_time'].shift(-1) - (ss['start_time'] + ss['duration'])
    # Add new columns using next row values
    ss['next_read_id'] = ss['read_id'].shift(-1)
    ss['next_start_time'] = ss['start_time'].shift(-1)
    ss['end_time'] = ss['start_time'] + ss['duration']
    ss['next_end'] = ss['next_start_time'] + ss['duration'].shift(-1)
    ss['next_sequence_length_template'] = ss['sequence_length_template'].shift(-1)
    ss['combined_length'] = ss['sequence_length_template'] + ss['next_sequence_length_template']
    # Fill blanks with zeros
    ss['next_sequence_length_template'] = ss['next_sequence_length_template'].fillna(0).astype('int64')
    ss['combined_length'] = ss['combined_length'].fillna(0).astype('int64')
    # Open paf file
    paf_file = args.paf
    pf = pd.read_csv(paf_file, sep='\t', header=None, usecols=[0, 4, 5, 7, 8])
    pf.columns = ['Qname', 'Strand', 'Tname', 'Tstart', 'Tend']
    """
    0		Query sequence name
    1x		Query sequence length
    2x		Query start coordinate (0-based)
    3x		Query end coordinate (0-based)
    4		`+' if query and target on the same strand; `-' if opposite
    5		Target sequence name (~chr)
    6x		Target sequence length
    7		Target start coordinate on the original strand
    8		Target end coordinate on the original strand
    9x		Number of matching bases in the mapping
    10x		Number bases, including gaps, in the mapping
    11x		Mapping quality (0-255 with 255 for missing)
    """
    # Merge sequencing summary and paf file twice: first on read_id, then on the following read id
    df = pd.merge(ss, pf, left_on='read_id', right_on='Qname', how='outer')
    df2 = pd.merge(df, pf, left_on='next_read_id', right_on='Qname', how='outer', suffixes=("_A", "_B"))
    df2 = df2.dropna().reset_index()

    not_qname = df2['Qname_A'] != df2['Qname_B']
    is_strand = df2['Strand_A'] == df2['Strand_B']
    is_tname = df2['Tname_A'] == df2['Tname_B']

    # Thin merged df2 where Qname doesn't match AND Strand matches AND Tname matches
    df2 = df2[not_qname & is_strand & is_tname]
    df2['match_distance'] = np.where(
        df2['Strand_A'] == '+',             # condition
        df2['Tstart_B'] - df2['Tend_A'],    # True
        df2['Tstart_A'] - df2['Tend_B']     # False
    )
    df2 = df2[df2['match_distance'] > 0]
    df2 = df2[df2['match_distance'] < args.distance]
    df2 = df2.drop_duplicates(subset=['channel', 'start_time', 'duration',
                                      'next_start_time', 'diff', 'read_id',
                                      'next_read_id', 'sequence_length_template',
                                      'next_sequence_length_template', 'combined_length'],
                              keep='first'
                              )

    cond_1 = df2['next_read_id'] == df2['read_id'].shift(-1)
    cond_2 = df2['read_id'] == df2['next_read_id'].shift(-1)

    df2['COND'] = np.where(cond_1 | cond_2, True, False)
    df2['W'] = np.where(df2['COND'].shift(1) == False, 1, 0)
    df2['cs'] = df2['W'].cumsum()
    df2 = df2.set_index('cs')

    df2['cat_read_id'] = df2.groupby(level='cs')['read_id'].apply('|'.join)
    df2['last_read_id'] = df2.groupby(level='cs')['next_read_id'].last()
    df2['cat_read_id'] = df2['cat_read_id'] + "|" + df2['last_read_id']

    df2['combined_length'] = df2.groupby(level='cs')['sequence_length_template'].sum()
    df2['last_length'] = df2.groupby(level='cs')['next_sequence_length_template'].last()
    df2['combined_length'] = df2['combined_length'] + df2['last_length']

    df2['start_match'] = df2.groupby(level='cs')['Tstart_A'].first()
    df2['end_match'] = df2.groupby(level='cs')['Tend_B'].last()

    df2['start_time'] = df2.groupby(level='cs')['start_time'].first()
    df2['next_end'] = df2.groupby(level='cs')['next_end'].last()
    df2['difference'] = df2['next_end'] - df2['start_time']
    df2['stime_floor'] = np.floor(df2['start_time']).astype('int64').astype('str')
    df2['etime_ceil'] = np.ceil(df2['next_end']).astype('int64').astype('str')
    df2['coords'] = df2['channel'].astype('int64').astype('str') + ":" + df2['stime_floor'] + "-" + df2['etime_ceil']

    df2['filename'] = df2['filename'].str.split('_read', 1).str[0]

    header = ['coords', 'filename', 'channel', 'start_time', 'next_end',
              'difference', 'combined_length', 'Tname_A', 'Strand_A',
              'start_match', 'end_match', 'cat_read_id']

    chained_read_ids = pd.concat([df2['read_id'], df2['next_read_id']])
    df2 = df2.drop_duplicates(subset=header, keep='first')

    chained_read_ids = chained_read_ids.unique()
    # ss2 is un-fused reads
    ss2 = ss[ss['read_id'].isin(chained_read_ids) == False]
    ss2 = ss2.reset_index()
    # ss3 is to-be-fused reads
    ss3 = ss[ss['read_id'].isin(chained_read_ids) == True]
    ss4 = ss3[ss3['read_id'].isin(df2['read_id']) == False]

    ss4.to_csv("to_be_fused.txt", sep="\t", header=True, columns=['channel', 'read_id', 'run_id', 'start_time'], index=False)
    ss2.to_csv("un_fused.txt", sep="\t", header=True, columns=['channel', 'read_id', 'run_id', 'start_time'], index=False)
    df2.to_csv("just_fused.txt", sep="\t", header=True, columns=['channel', 'read_id', 'run_id', 'start_time'], index=False)


def get_args():
    parser = ArgumentParser(
        description="""Parse sequencing_summary.txt files 
                       and .paf files to find chained reads 
                       in an Oxford Nanopore Dataset""",
        add_help=False)
    general = parser.add_argument_group(
        title='General options')
    general.add_argument("-h", "--help",
                         action="help",
                         help="Show this help and exit"
                         )
    general.add_argument("-d", "--distance",
                         help='''Specify the maximum distance between consecutive mappings.
                              This is the difference between \'Target Start\' and \'Target End\' in 
                              the paf file. Defaults to 10000''',
                         type=int,
                         default=10000,
                         metavar=''
                         )
    in_args = parser.add_argument_group(
        title='Input sources'
    )
    in_args.add_argument("-s", "--summary",
                         help="A sequencing summary file generated by albacore",
                         type=str,
                         default="",
                         required=True,
                         metavar=''
                         )
    in_args.add_argument("-p", "--paf",
                         help="A paf file generated by minimap2",
                         type=str,
                         default='',
                         required=True,
                         metavar=''
                         )
    out_args = parser.add_argument_group(
        title='Output files'
    )
    out_args.add_argument('-S', '--out-summary',
                          help='''Specify the name of the complete fused read file. This file contains all reads from 
                               sequencing_summary.txt and chains of reads.''',
                          type=str,
                          default='fused_summary.txt',
                          metavar=''
                          )
    out_args.add_argument('-F', '--out-fused',
                          help='''Specify name of the fused_read file. This file only contains chains of reads. 
                               Defaults to \'fused_reads.txt\'''',
                          type=str,
                          default='fused_reads.txt',
                          metavar=''
                          )
    return parser.parse_args()


if __name__ == '__main__':
    main()