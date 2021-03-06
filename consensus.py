#!/usr/bin/env python
#  -*- coding: utf-8 -*-
"""
Consensus tools

Contains functions that compute consensus sequences in small windows accross a given connected component (contig),
and then functions that merge together those consensus sequences to get a full contig-long consensus sequence.

The consensus sequences are generated by multiple sequence alignment
through a partial order graph (https://sourceforge.net/projects/poamsa/).
The software spoa (https://github.com/rvaser/spoa) is called for this purpose.

Some parts of this code are inspired from nanocorrect (https://github.com/jts/nanocorrect)

@author: Antoine Recanati
"""
from __future__ import print_function
import sys
import os
import numpy as np
import subprocess
from functools import partial
from multiprocessing import Pool

from ioandplots import make_dir, oprint


### These functions are designed to compute consensus sequences in small windows for each contig.

def run_spoa(filename, spoa_path, reads_fmt):
    """ Runs multiple sequence alignment with spoa.

    Parameters
    ----------
    filename : str (path to fasta file with sequences to align)
    spoa_path : str (path to spoa executable [from https://github.com/rvaser/spoa])
    reads_fmt : str ('fasta' or 'fastq')

    """

    # Check that file exists and is not empty
    if (not(os.path.exists(filename)) or os.path.getsize(filename)==0):
        return

    # Run spoa
    cmd = [spoa_path, '-%s' % reads_fmt[-1], filename,
           '-l', '2', '-r', '0', '-x', '-3', '-o', '-5', '-e', '-2']

    out_f = "%s.cnsns" % filename
    out_fh = open(out_f, 'wb')
    subprocess.call(cmd, stderr=out_fh)
    out_fh.close()

    return



def fill_window(w_idx, record_list, cc_idx, cc, bpos_list,
epos_list, opts):
    """ Writes pieces of sequences that fits in the current window to a .fasta file for multiple sequence alignment.

    Parameters
    ----------
    w_idx : int (current window number)
    record_list : list (reads in SeqIO record format)
    cc_idx : int (index of the connected component)
    cc : list (index of the reads in the cc_idx-th connected component)
    bpos_list : numpy.ndarray (leftmost base coordinate of the reads in the connected component)
    opts : dict (keywords arguments for global parameters)

    """
    # retrieve options from opts dictionary
    W_LEN = opts['W_LEN']
    W_OVL_LEN = opts['W_OVL_LEN']
    READS_FMT = opts['READS_FMT']

    w_b = (W_LEN - W_OVL_LEN) * w_idx
    w_e = w_b + W_LEN
    reads_in_w = np.flatnonzero((bpos_list < w_e)*(epos_list > w_b))

    cc_dir = "%s/cc_%d" % (opts['ROOT_DIR'], cc_idx)
    in_fn = cc_dir + "/poa_in_cc_%d_win_%d.%s" % (cc_idx, w_idx, READS_FMT)
    in_fh = open(in_fn, 'wb')
    for idx in reads_in_w:
        read_idx = cc[idx]
        record = record_list[read_idx]

        # Trim read to the part contained in the window
        read_len = len(record.seq)
        bb = int(max(0, w_b - bpos_list[idx]))
        ee = int(min(read_len, w_e - bpos_list[idx]))

        # Do not add too small pieces of sequence
        if ee - bb < 20:
            continue

        # Write to poa_in file
        seqfmtd = record[bb:ee].format(READS_FMT)
        in_fh.write(seqfmtd)

    in_fh.close()
    return

def fill_and_run_spoa(w_idx, record_list, cc_idx, cc, bpos_list,
epos_list, opts):
    """ Writes pieces of sequences that fits in the current window to a .fasta file for multiple sequence alignment.

    Parameters
    ----------
    w_idx : int (current window number)
    record_list : list (reads in SeqIO record format)
    cc_idx : int (index of the connected component)
    cc : list (index of the reads in the cc_idx-th connected component)
    bpos_list : numpy.ndarray (leftmost base coordinate of the reads in the connected component)
    opts : dict (keywords arguments for global parameters)

    """
    # retrieve options from opts dictionary
    W_LEN = opts['W_LEN']
    W_OVL_LEN = opts['W_OVL_LEN']
    READS_FMT = opts['READS_FMT']

    w_b = (W_LEN - W_OVL_LEN) * w_idx
    w_e = w_b + W_LEN
    reads_in_w = np.flatnonzero((bpos_list < w_e)*(epos_list > w_b))

    cc_dir = "%s/cc_%d" % (opts['ROOT_DIR'], cc_idx)
    in_fn = cc_dir + "/poa_in_cc_%d_win_%d.%s" % (cc_idx, w_idx, READS_FMT)
    in_fh = open(in_fn, 'wb')
    for idx in reads_in_w:
        read_idx = cc[idx]
        record = record_list[read_idx]

        # Trim read to the part contained in the window
        read_len = len(record.seq)
        bb = int(max(0, w_b - bpos_list[idx]))
        ee = int(min(read_len, w_e - bpos_list[idx]))

        # Do not add too small pieces of sequence
        if ee - bb < 20:
            continue

        # Write to poa_in file
        seqfmtd = record[bb:ee].format(READS_FMT)
        in_fh.write(seqfmtd)

    in_fh.close()

    run_spoa(in_fn, opts['SPOA_PATH'], opts['READS_FMT'])

    return



def run_spoa_in_cc(record_list, cc_idx, cc, strand_list, bpos_list,
epos_list, opts):
    """ Split connected component in windows and compute multiple sequence alignment in each window
    with spoa.

    Parameters
    ----------
    record_list : list (reads in SeqIO record format)
    cc_idx : int (index of the connected component)
    cc : list (index of the reads in the cc_idx-th connected component)
    strand_list : numpy.ndarray (strands of the reads in the connected component)
    bpos_list : numpy.ndarray (leftmost base coordinate of the reads in the connected component)
    epos_list : numpy.ndarray (rightmost base coordinate of the reads in the connected component)
    opts : dict (keywords arguments for global parameters)

    """
    # retrieve options from opts dictionary
    W_LEN = opts['W_LEN']
    W_OVL_LEN = opts['W_OVL_LEN']
    N_PROC = opts['N_PROC']
    ROOT_DIR = opts['ROOT_DIR']
    # SPOA_PATH = opts['SPOA_PATH']
    # READS_FMT = opts['READS_FMT']

    # Make cc_dir dictionary if not existent
    cc_dir = "%s/cc_%d" % (ROOT_DIR, cc_idx)
    make_dir(cc_dir)

    # Offset of bpos_list set to 0
    cons_len = epos_list.max() - bpos_list.min()
    b_min = bpos_list.min()
    bpos_list = bpos_list - b_min
    epos_list = epos_list - b_min
    n_windows = cons_len // (W_LEN - W_OVL_LEN)
    n_windows = int(n_windows + 1)

    # Reverse complement reads on opposite strand
    for (idx, read_idx) in enumerate(cc):
        if not strand_list[idx]:
            read_id = record_list[read_idx].id
            record_list[read_idx] = record_list[read_idx].reverse_complement()
            record_list[read_idx].id = read_id

    if N_PROC > 1:
        fill_and_run = partial(fill_and_run_spoa,
        record_list=record_list, cc_idx=cc_idx, cc=cc, bpos_list=bpos_list,
        epos_list=epos_list, opts=opts)
        mypool = Pool(processes=N_PROC)
        mypool.map(fill_and_run, range(n_windows))
        mypool.close()
        mypool.join()

    # # Define run_spoa function with SPOA_PATH and READS_FMT fixed
    # partial_run_spoa = partial(run_spoa, spoa_path=SPOA_PATH,
    #                            reads_fmt=READS_FMT)
    #
    # for w_idx in xrange(n_windows):
    #
    #     in_fn = cc_dir + "/poa_in_cc_%d_win_%d.%s" % (cc_idx, w_idx, READS_FMT)
    #
    #     fill_window(w_idx, record_list, cc_idx, cc,
    #                 bpos_list, epos_list, opts)
    #     if N_PROC == 1:
    #         run_spoa(in_fn, SPOA_PATH, READS_FMT)
    #     else:
    #         mypool.apply_async(partial_run_spoa, args=(in_fn,))
    #
    # if N_PROC > 1:
    #     mypool.close()
    #     mypool.join()
    #
    return


### Those functions are designed to merge the consensus sequences from all windows into one sequence per contig.

def get_consensus(out_fn, trim_margin):
    """ Extract consensus sequence from output of spoa.

    Parameters
    ----------
    out_fn : str (output from spoa)
    trim_margin : int (number of bp to trim on each end of the consensus, as the consensus sequence
    is more likely to be erroneous on the ends)

    Returns
    -------
    consensus : str (consensus sequence)

    """
    fh = open(out_fn, 'rb')
    lines = fh.readlines()
    if len(lines) == 0:
        return ''
    consensus = lines[-1][:-1]
    consensus = consensus[trim_margin:len(consensus) - trim_margin]
    fh.close()
    return consensus


def run_spoa_and_consensus(in_fn, out_fn, spoa_path):
    """ Runs multiple sequence alignment with spoa on fasta file in_fn, prints output to out_fn,
    and return consensus sequence.

    Parameters
    ----------
    in_fn : str (input for spoa)
    out_fn : str (output from spoa)
    spoa_path : str (path to spoa executable)

    Returns
    -------
    consensus : str (consensus sequence)

    """

    # Check that file exists and is not empty
    # ! Should add a safeguard to stop also if empty sequence
    if (not(os.path.exists(in_fn)) or os.path.getsize(in_fn)==0):
        return ''

    # Run spoa
    cmd = "%s -%s %s -r 0 -l 2 >& %s" % (spoa_path, 'a', in_fn, out_fn)
    p = subprocess.Popen(cmd, shell=True)
    p.wait()
    consensus = get_consensus(out_fn, 0)
    os.remove(in_fn)
    os.remove(out_fn)

    return consensus


def add_next_window(temp_fn, w_idx, cc_idx, whole_cons, opts, trim_margin):
    """ Add the consensus from the current window to the current consensus.

    Parameters
    ----------
    temp_fn : str (temporary file to write sequences to align with spoa)
    w_idx : int (index of current window)
    cc_idx : int (index of the connected component)
    whole_cons : str (consensus extracted so far by joining the consensus sequences from windows 0 to w_idx - 1)
    opts : dict (keywords arguments for global parameters)
    trim_margin : int (number of bp to trim on each end of the consensus, as the consensus sequence
    is more likely to be erroneous on the ends)

    Returns
    -------
    str (consensus extracted by joining the consensus sequences from windows 0 to w_idx)
    """
    DATATYPE = opts['READS_FMT'][-1]
    ROOT_DIR = opts['ROOT_DIR']
    MERGE_MARGIN = opts['MERGE_MARGIN']
    VERB = opts['VERB']

    fn = "%s/cc_%d/poa_in_cc_%d_win_%d.fast%s.cnsns" % (ROOT_DIR, cc_idx, cc_idx, w_idx, DATATYPE)
    if (not(os.path.exists(fn)) or os.path.getsize(fn)==0):
        msg = "file %s does not exist or is empty" % (fn)
        oprint(msg, cond=(VERB >= 2))
        return whole_cons

    next_win_seq = get_consensus(fn, trim_margin)
    next_win_len = len(next_win_seq)
    whole_cons_len = len(whole_cons)
    kept_len = max(0, whole_cons_len - next_win_len - MERGE_MARGIN)
    cons0 = whole_cons[:kept_len]
    cons1 = whole_cons[kept_len:]

    # Write end of current consensus long sequence and next consensus window sequence in poa_in file
    poa_in_fh = open(temp_fn, "wb")
    poa_in_fh.write(">end_of_current_cons\n%s\n" % (cons1))
    poa_in_fh.write(">cons_in_window_%d\n%s\n" % (w_idx, next_win_seq))
    poa_in_fh.close()
    # Run poa to include next
    out_fn = "%s/cc_%d/poa_out_cons_cc%d_win_%d" % (ROOT_DIR, cc_idx, cc_idx, w_idx)
    cons1b = run_spoa_and_consensus(temp_fn, out_fn, opts['SPOA_PATH'])

    return cons0 + cons1b


def merge_windows_in_cc(cc_idx, opts):
    """ Merge the consensus sequences from all windows into one sequence (contig).

    Parameters
    ----------
    cc_idx : int (index of the connected component)
    opts : dict (keywords arguments for global parameters)

    """
    # Parse arguments
    TRIM_MARGIN = opts['TRIM_MARGIN']
    DATATYPE = opts['READS_FMT'][-1]
    ROOT_DIR = opts['ROOT_DIR']
    VERB = opts['VERB']

    # Count number of windows
    try:
        cmd = "ls %s/cc_%d/poa_in_cc_%d_win_*.fast*.cnsns | wc -l" % (ROOT_DIR, cc_idx, cc_idx)
        n_win = int(subprocess.check_output(cmd, shell=True))
    except:
        n_win = 10000  # quick fix in case of problem with output of subprocess

    # Initialize
    fn = "%s/cc_%d/poa_in_cc_%d_win_%d.fast%s.cnsns" % (ROOT_DIR, cc_idx, cc_idx, 0, DATATYPE)
    whole_cons = get_consensus(fn, TRIM_MARGIN)
    oprint(len(whole_cons))

    # Incrementally add consensus between window k and window k+1
    # trim margin = 0 for first and last 3 windows
    for w_idx in xrange(0, 3):
        poa_in_fn = "%s/poa_in_cons_cc_%d_win_%d.fasta" % (ROOT_DIR, cc_idx, w_idx)
        whole_cons = add_next_window(poa_in_fn, w_idx, cc_idx, whole_cons, opts, 0)

    # trim margin = args.trim_margin for the rest of the windows
    for w_idx in xrange(3, n_win - 3):
        poa_in_fn = "%s/poa_in_cons_cc_%d_win_%d.fasta" % (ROOT_DIR, cc_idx, w_idx)
        whole_cons = add_next_window(poa_in_fn, w_idx, cc_idx, whole_cons, opts, TRIM_MARGIN)
        msg = "Consensus generation... %dbp extracted so far (window %d)" % (len(whole_cons), w_idx)
        condition = (VERB >= 2) and (w_idx % 500 == 0)
        oprint(msg, cond=condition)

    for w_idx in xrange(n_win - 3, n_win):
        poa_in_fn = "%s/poa_in_cons_cc_%d_win_%d.fasta" % (ROOT_DIR, cc_idx, w_idx)
        whole_cons = add_next_window(poa_in_fn, w_idx, cc_idx, whole_cons, opts, 0)

    msg = "extracted and merged sequences in windows for contig %d. Consensus length %dbp" % \
          (cc_idx, len(whole_cons))
    oprint(msg, cond=(VERB >= 2))

    # Print consensus to backup file
    consensus_fn = "%s/consensus_cc_%d.fasta" % (ROOT_DIR, cc_idx)
    consensus_fh = open(consensus_fn, "wb")
    consensus_fh.write(">consensus_from_windows_contig_%d\n%s\n" % (cc_idx, whole_cons))
    consensus_fh.close()

    # print(">contig_%d\n%s" % (cc_idx, whole_cons), file=sys.stdout)

    return whole_cons
