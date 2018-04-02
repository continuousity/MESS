#!/usr/bin/env python2
""" the main CLI for calling ipyrad """

from __future__ import print_function, division  # Requires Python 2.7+

import argparse
import logging
import atexit
import time
import sys
import os

def parse_params(args):
    """ Parse the params file args, create and return Assembly object."""

    ## check that params.txt file is correctly formatted.
    try:
        with open(args.params) as paramsin:
            plines = paramsin.readlines()
    except IOError as _:
        sys.exit("  No params file found")

    ## check header: big version changes can be distinguished by the header
    legacy_version = 0
    try:
        ## try to update the Assembly ...
        legacy_version = 1
        if not len(plines[0].split()[0]) == 7:
            raise IPyradWarningExit("""
        Error: file '{}' is not compatible with ipyrad v.{}.
        Please create and update a new params file using the -n argument. 
        For info on which parameters have changed see the changelog:
        (http://ipyrad.readthedocs.io/releasenotes.html)
        """.format(args.params, ip.__version__))

    except IndexError:
        raise IPyradWarningExit("""
        Error: Params file should not have any empty lines at the top
        of the file. Verify there are no blank lines and rerun ipyrad.
        Offending file - {}
        """.format(args.params))

    ## update and backup
    if legacy_version:
        #which version...
        #update_to_6()
        pass

    ## make into a dict. Ignore blank lines at the end of file
    ## Really this will ignore all blank lines
    items = [i.split("##")[0].strip() for i in plines[1:] if not i.strip() == ""]

    #keys = [i.split("]")[-2][-1] for i in plines[1:]]
    #keys = range(len(plines)-1)
    keys = ip.Assembly('null', quiet=True).paramsdict.keys()
    parsedict = {str(i):j for i, j in zip(keys, items)}
    return parsedict



def showstats(parsedict):
    """ loads assembly or dies, and print stats to screen """

    #project_dir = parsedict['1']
    project_dir = parsedict["project_dir"]
    if not project_dir:
        project_dir = "./"
    ## Be nice if somebody also puts in the file extension
    #assembly_name = parsedict['0']
    assembly_name = parsedict["assembly_name"]
    my_assembly = os.path.join(project_dir, assembly_name)

    ## If the project_dir doesn't exist don't even bother trying harder.
    if not os.path.isdir(project_dir):
        msg = """
    Trying to print stats for Assembly ({}) that doesn't exist. You must 
    first run steps before you can show results.
    """.format(project_dir)
        sys.exit(msg)

    if not assembly_name:
        msg = """
    Assembly name is not set in params.txt, meaning it was either changed or
    erased since the Assembly was started. Please restore the original name. 
    You can find the name of your Assembly in the "project dir": {}.
    """.format(project_dir)
        raise IPyradError(msg)

    data = ip.load_json(my_assembly, quiet=True, cli=True)

    print("\nSummary stats of Assembly {}".format(data.name) \
         +"\n------------------------------------------------")
    
    if not data.stats.empty:
        print(data.stats)
        print("\n\nFull stats files"\
         +"\n------------------------------------------------")

        fullcurdir = os.path.realpath(os.path.curdir)
        for i in range(1, 8):
            #enumerate(sorted(data.stats_files)):
            key = "s"+str(i)
            try:
                val = data.stats_files[key]
                val = val.replace(fullcurdir, ".")                
                print("step {}: {}".format(i, val))
            except (KeyError, AttributeError):
                print("step {}: None".format(i))
        print("\n")
    else:
        print("No stats to display")



def branch_assembly(args, parsedict):
    """ 
    Load the passed in assembly and create a branch. Copy it
    to a new assembly, and also write out the appropriate params.txt
    """

    ## Get the current assembly
    data = getassembly(args, parsedict)


    ## get arguments to branch command
    bargs = args.branch

    ## get new name, trim off .txt if it was accidentally added
    newname = bargs[0]
    if newname.endswith(".txt"):
        newname = newname[:-4]

    ## look for subsamples
    if len(bargs) > 1:
        ## Branching and subsampling at step 6 is a bad idea, it messes up
        ## indexing into the hdf5 cluster file. Warn against this.
        if any([x.stats.state == 6 for x in data.samples.values()]):
            pass
            ## TODODODODODO
            #print("wat")

        ## are we removing or keeping listed samples?
        subsamples = bargs[1:]

        ## drop the matching samples
        if bargs[1] == "-":
            ## check drop names
            fails = [i for i in subsamples[1:] if i not in data.samples.keys()]
            if any(fails):
                raise IPyradWarningExit("\
                    \n  Failed: unrecognized names requested, check spelling:\n  {}"\
                    .format("\n  ".join([i for i in fails])))
            print("  dropping {} samples".format(len(subsamples)-1))
            subsamples = list(set(data.samples.keys()) - set(subsamples))

        ## If the arg after the new param name is a file that exists
        if os.path.exists(bargs[1]):
            new_data = data.branch(newname, infile=bargs[1])
        else:
            new_data = data.branch(newname, subsamples)

    ## keeping all samples
    else:
        new_data = data.branch(newname, None)

    print("  creating a new branch called '{}' with {} Samples".\
             format(new_data.name, len(new_data.samples)))

    print("  writing new params file to {}"\
            .format("params-"+new_data.name+".txt\n"))
    new_data.write_params("params-"+new_data.name+".txt", force=args.force)



def merge_assemblies(args):
    """ 
    merge all given assemblies into a new assembly. Copies the params
    from the first passed in extant assembly. this function is called 
    with the ipyrad -m flag. You must pass it at least 3 values, the first
    is a new assembly name (a new `param-newname.txt` will be created).
    The second and third args must be params files for currently existing
    assemblies. Any args beyond the third must also be params file for
    extant assemblies.
    """
    print("\n  Merging assemblies: {}".format(args.merge[1:]))

    ## Make sure there are the right number of args
    if len(args.merge) < 3:
        sys.exit(_WRONG_NUM_CLI_MERGE)

    ## Make sure the first arg isn't a params file, i could see someone doing it
    newname = args.merge[0]
    if os.path.exists(newname) and "params-" in newname:
        sys.exit(_WRONG_ORDER_CLI_MERGE) 

    ## Make sure first arg will create a param file that doesn't already exist
    if os.path.exists("params-" + newname + ".txt") and not args.force:
        sys.exit(_NAME_EXISTS_MERGE.format("params-" + newname + ".txt"))

    ## Make sure the rest of the args are params files that already exist
    assemblies_to_merge = args.merge[1:]
    for assembly in assemblies_to_merge:
        if not os.path.exists(assembly):
            sys.exit(_DOES_NOT_EXIST_MERGE.format(assembly))

    ## Get assemblies for each of the passed in params files.
    ## We're recycling some of the machinery for loading assemblies here
    assemblies = []
    for params_file in args.merge[1:]:
        args.params = params_file
        parsedict = parse_params(args)
        assemblies.append(getassembly(args, parsedict))

    ## Do the merge
    merged_assembly = ip.merge(newname, assemblies)

    ## Write out the merged assembly params file and report success
    merged_assembly.write_params("params-{}.txt".format(newname), force=args.force)

    print("\n  Merging succeeded. New params file for merged assembly:")
    print("\n    params-{}.txt\n".format(newname))



def getassembly(args, parsedict):
    """ 
    loads assembly or creates a new one and set its params from 
    parsedict. Does not launch ipcluster. 
    """

    ## Creating an assembly with a full path in the name will "work"
    ## but it is potentially dangerous, so here we have assembly_name
    ## and assembly_file, name is used for creating new in cwd, file is
    ## used for loading existing.
    ##
    ## Be nice if the user includes the extension.
    #project_dir = ip.core.assembly._expander(parsedict['1'])
    #assembly_name = parsedict['0']
    project_dir = ip.core.assembly._expander(parsedict['project_dir'])
    assembly_name = parsedict['assembly_name']
    assembly_file = os.path.join(project_dir, assembly_name)

    ## Assembly creation will handle error checking  on
    ## the format of the assembly_name

    ## make sure the working directory exists.
    if not os.path.exists(project_dir):
        os.mkdir(project_dir)

    try:
        ## If 1 and force then go ahead and create a new assembly
        if ('1' in args.steps) and args.force:
            data = ip.Assembly(assembly_name, cli=True)
        else:
            data = ip.load_json(assembly_file, cli=True)
            data._cli = True

    except IPyradWarningExit as _:
        ## if no assembly is found then go ahead and make one
        if '1' not in args.steps:
            raise IPyradWarningExit(\
                "  Error: You must first run step 1 on the assembly: {}"\
                .format(assembly_file))
        else:
            ## create a new assembly object
            data = ip.Assembly(assembly_name, cli=True)

    ## for entering some params...
    for param in parsedict:

        ## trap assignment of assembly_name since it is immutable.
        if param == "assembly_name":
            ## Raise error if user tried to change assembly name
            if parsedict[param] != data.name:
                data.set_params(param, parsedict[param])
        else:
            ## all other params should be handled by set_params
            try:
                data.set_params(param, parsedict[param])
            except IndexError as _:
                print("  Malformed params file: {}".format(args.params))
                print("  Bad parameter {} - {}".format(param, parsedict[param]))
                sys.exit(-1)
    return data



def _check_version():
    """ Test if there's a newer version and nag the user to upgrade."""
    import urllib2
    from distutils.version import LooseVersion

    header = \
    "\n -------------------------------------------------------------"+\
    "\n  ipyrad [v.{}]".format(ip.__version__)+\
    "\n  Interactive assembly and analysis of RAD-seq data"+\
    "\n -------------------------------------------------------------"

    try:
        htmldat = urllib2.urlopen("https://anaconda.org/ipyrad/ipyrad").readlines()
        curversion = next((x for x in htmldat if "subheader" in x), None).split(">")[1].split("<")[0]
        if LooseVersion(ip.__version__) < LooseVersion(curversion):
            msg = """
  A new version of ipyrad is available (v.{}). To upgrade run:

    conda install -c ipyrad ipyrad\n""".format(curversion)
            print(header + "\n" + msg)
        else:
            pass
            #print("You are up to date")
    except Exception as inst:
        ## Always fail silently
        pass



def parse_command_line():
    """ Parse CLI args."""

    ## create the parser
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\n
  * Example command-line usage: 
    MESS -n data                       ## create new file called params-data.txt 
    MESS -p params-data.txt            ## run MESS with settings in params file
    MESS -p params-data.txt -f         ## run MESS, overwrite existing data.
    """)

    #* Preview mode (subsamples data)
    #  ipyrad -p params-data.txt -s --preview  

    ## add arguments 
    #parser.add_argument('-v', '--version', action='version', 
    #    version=str(pkg_resources.get_distribution('ipyrad')))

    parser.add_argument('-f', "--force", action='store_true',
        help="force overwrite of existing data")

    parser.add_argument('-q', "--quiet", action='store_true',
        help="do not print to stderror or stdout.")

    parser.add_argument('-d', "--debug", action='store_true',
        help="print lots more info to ipyrad_log.txt.")

    parser.add_argument('-n', metavar='new', dest="new", type=str, 
        default=None, 
        help="create new file 'params-{new}.txt' in current directory")

    parser.add_argument('-p', metavar='params', dest="params",
        type=str, default=None,
        help="path to params file simulations: params-{assembly_name}.txt")

    parser.add_argument("-c", metavar="cores", dest="cores",
        type=int, default=0,
        help="number of CPU cores to use (Default=0=All)")

    #parser.add_argument("--ipcluster", metavar="ipcluster", dest="ipcluster",
    #    type=str, nargs="?", const="default",
    #    help="connect to ipcluster profile (default: 'default')")

    ## if no args then return help message
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    ## parse args
    args = parser.parse_args()

    if not any(x in ["params", "new"] for x in vars(args).keys()):
        print("Bad arguments: must include at least one of"\
                +"`-p` or `-n`\n")
        parser.print_help()
        sys.exit(1)

    return args



def main():
    """ main function """
    ## parse params file input (returns to stdout if --help or --version)
    args = parse_command_line()

    ## create new paramsfile if -n
    if args.new:
        ## Create a tmp assembly, call write_params to make default params.txt
        try:
            tmpassembly = ip.Assembly(args.new, quiet=True, cli=True)
            tmpassembly.write_params("params-{}.txt".format(args.new), 
                                     force=args.force)
        except Exception as inst:
            print(inst)
            sys.exit(2)

        print("\n  New file 'params-{}.txt' created in {}\n".\
               format(args.new, os.path.realpath(os.path.curdir)))
        sys.exit(2)


    ## if params then must provide action argument with it
    if args.params:
        if not any([args.branch, args.results, args.steps]):
            print("""
    Must provide action argument along with -p argument for params file. 
    e.g., ipyrad -p params-test.txt -r              ## shows results
    e.g., ipyrad -p params-test.txt -s 12           ## runs steps 1 & 2
    e.g., ipyrad -p params-test.txt -b newbranch    ## branch this assembly
    """)
            sys.exit(2)

    if not args.params:
        if any([args.branch, args.results, args.steps]):
            print("""
    Must provide params file for branching, doing steps, or getting results.
    e.g., ipyrad -p params-test.txt -r              ## shows results
    e.g., ipyrad -p params-test.txt -s 12           ## runs steps 1 & 2
    e.g., ipyrad -p params-test.txt -b newbranch    ## branch this assembly
    """)

    ## if branching, or merging do not allow steps in same command
    ## print spacer
    if any([args.branch, args.merge]):        
        args.steps = ""    
        print("")    

    ## always print the header when doing steps
    header = \
    "\n -------------------------------------------------------------"+\
    "\n  MESS [v.{}]".format(ip.__version__)+\
    "\n  Massive Eco-Evolutionary Synthesis Simulations"+\
    "\n -------------------------------------------------------------"

    ## Log the current version. End run around the LOGGER
    ## so it'll always print regardless of log level.
    with open(ip.__debugfile__, 'a') as logfile:
        logfile.write(header)
        logfile.write("\n  Begin run: {}".format(time.strftime("%Y-%m-%d %H:%M")))
        logfile.write("\n  Using args {}".format(vars(args)))
        logfile.write("\n  Platform info: {}".format(os.uname()))

    ## if merging just do the merge and exit
    if args.merge:
        print(header)
        merge_assemblies(args)
        sys.exit(1)

    ## if download data do it and then exit. Runs single core in CLI. 
    if args.download:
        if len(args.download) == 1:
            downloaddir = "sra-fastqs"
        else:
            downloaddir = args.download[1]
        sratools_download(args.download[0], workdir=downloaddir, force=args.force)
        sys.exit(1)

    ## create new Assembly or load existing Assembly, quit if args.results
    elif args.params:
        parsedict = parse_params(args)

        if args.branch:
            branch_assembly(args, parsedict)

        elif args.steps:
            ## print header
            print(header)

            ## Only blank the log file if we're actually going to run a new
            ## assembly. This used to be in __init__, but had the side effect
            ## of occasionally blanking the log file in an undesirable fashion
            ## for instance if you run a long assembly and it crashes and
            ## then you run `-r` and it blanks the log, it's crazymaking.
            if os.path.exists(ip.__debugfile__):
                if os.path.getsize(ip.__debugfile__) > 50000000:
                    with open(ip.__debugfile__, 'w') as clear:
                        clear.write("file reset")

            ## run Assembly steps
            ## launch or load assembly with custom profile/pid
            data = getassembly(args, parsedict)

            ## set CLI ipcluster terms
            data._ipcluster["threads"] = args.threads

            ## if ipyclient is running (and matched profile) then use that one
            if args.ipcluster:
                ipyclient = ipp.Client(profile=args.ipcluster)
                data._ipcluster["cores"] = len(ipyclient)

            ## if not then we need to register and launch an ipcluster instance
            else:
                ## set CLI ipcluster terms
                ipyclient = None
                data._ipcluster["cores"] = args.cores if args.cores else detect_cpus()
                data._ipcluster["engines"] = "Local"
                if args.MPI:
                    data._ipcluster["engines"] = "MPI"
                    if not args.cores:
                        raise IPyradWarningExit("must provide -c argument with --MPI")
                ## register to have a cluster-id with "ip- name"
                data = register_ipcluster(data)

            ## set to print headers
            data._headers = 1

            ## run assembly steps
            steps = list(args.steps)
            data.run(
                steps=steps, 
                force=args.force, 
                preview=args.preview, 
                show_cluster=1, 
                ipyclient=ipyclient)
                     
        if args.results:
            showstats(parsedict)


__PARAMSFILE_TPL="""## MESS Model v.0.0.1 Parameters file ##"""



if __name__ == "__main__": 
    main()
