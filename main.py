import configparser
from dateutil import parser
import math
from pathlib import Path
import re
from collections import OrderedDict

import h5py
import numpy as np
import pandas as pd
from bokeh.layouts import row, widgetbox
from bokeh.models import TextInput, Toggle, Div, Range1d, Label, Span, Title
from bokeh.models import CheckboxGroup, Dropdown, PreText, Select, Button, ColumnDataSource
from bokeh.plotting import curdoc, figure
from utils.stitch import export_read_file

config = configparser.ConfigParser()
config.read(Path(Path(__file__).resolve().parent / 'config.ini'))
cfg_po = config['plot_opts']
cfg_dr = config['data']
cfg_lo = config['labels']


"""

PUT IN A CHECK THAT REQUIRED CFG PARAMS ARE SET!!!!

if cfg_dr[out] == '':
    disable read-file write function <- remove button

"""

output_backend = {'canvas', 'svg', 'webgl'}


def init_wdg_dict():
    wdg_dict = OrderedDict()
    wdg_dict['file_list'] = Select(title="Select file:", options=app_data['app_vars']['files'])
    wdg_dict['file_list'].on_change('value', update_file)
    return wdg_dict


def update_file(attr, old, new):
    """"""
    if app_data['bulkfile']:
        app_data['bulkfile'].flush()
        app_data['bulkfile'].close()

    if new == "":
        app_data['wdg_dict'] = init_wdg_dict()
        f = figure(toolbar_location=None)
        f.outline_line_color = None
        f.toolbar.logo = None
        f.xaxis.visible = False
        f.yaxis.visible = False
        layout.children[0] = widgetbox(list(app_data['wdg_dict'].values()), width=int(cfg_po['wdg_width']))
        layout.children[1] = f
        return

    file_src = app_data['wdg_dict']['file_list'].value
    file_wdg = app_data['wdg_dict']['file_list']
    file_list = app_data['app_vars']['files']
    # Clear old bulkfile data and build new data structures
    app_data.clear()
    app_data['app_vars'] = {}
    app_data['wdg_dict'] = OrderedDict()
    app_data['label_dt'] = OrderedDict()
    app_data['file_src'] = Path(Path(cfg_dr['dir']) / file_src)
    app_data['INIT'] = True
    app_data['app_vars']['files'] = file_list

    (app_data['bulkfile'],
     app_data['app_vars']['sf'],
     app_data['app_vars']['channel_list']) = open_bulkfile(app_data['file_src'])

    raw_path = app_data['bulkfile']["Raw"]
    for i, member in enumerate(raw_path):
        if i == 0:
            signal_ds = raw_path[member]["Signal"][()]
            # get dataset length in seconds
            # app_data['app_vars']['len_ds'] = math.ceil(len(signal_ds) / app_data['app_vars']['sf'])
            app_data['app_vars']['len_ds'] = len(signal_ds) / app_data['app_vars']['sf']

    # add fastq and position inputs
    app_data['wdg_dict'] = init_wdg_dict()
    app_data['wdg_dict']['file_list'] = file_wdg
    app_data['wdg_dict']['position_label'] = Div(text='Position', css_classes=['position-dropdown', 'help-text'])
    app_data['wdg_dict']['position_text'] = Div(
        text="""Enter a position in your bulkfile as <code>channel:start_time-end_time</code> or a
                <code>complete FASTQ header</code>.
                """,
        css_classes=['position-drop']
    )
    app_data['wdg_dict']['position'] = TextInput(
        value="",
        placeholder="e.g 391:120-150 or complete FASTQ header",
        css_classes=['position-label']
    )

    app_data['wdg_dict']['position'].on_change("value", parse_position)

    layout.children[0] = widgetbox(list(app_data['wdg_dict'].values()), width=int(cfg_po['wdg_width']))


def open_bulkfile(path):
    """"""
    # !!! add in check to see if this is a ONT bulkfile
    # Open bulkfile in read-only mode
    file = h5py.File(path, "r")
    # Get sample frequency, how many data points are collected each second
    sf = int(file["UniqueGlobalKey"]["context_tags"].attrs["sample_frequency"].decode('utf8'))
    # make channel_list
    channel_list = np.arange(1, len(file["Raw"]) + 1, 1).tolist()
    try:
        # Experiment
        app_data['app_vars']['exp'] = file["UniqueGlobalKey"]["tracking_id"].attrs["sample_id"].decode('utf8')
    except KeyError:
        app_data['app_vars']['exp'] = "NA"
    try:
        # Flowcell ID
        app_data['app_vars']['fc_id'] = file["UniqueGlobalKey"]["tracking_id"].attrs["flow_cell_id"].decode('utf8')
    except KeyError:
        app_data['app_vars']['fc_id'] = "NA"
    try:
        # MinKNOW version
        app_data['app_vars']['mk_ver'] = file["UniqueGlobalKey"]["tracking_id"].attrs["version"].decode('utf8')
    except KeyError:
        app_data['app_vars']['mk_ver'] = "NA"
    try:
        # MinION ID
        app_data['app_vars']['m_id'] = file["UniqueGlobalKey"]["tracking_id"].attrs["device_id"].decode('utf8')
    except KeyError:
        app_data['app_vars']['m_id'] = "NA"
    try:
        # Hostname
        app_data['app_vars']['hn'] = file["UniqueGlobalKey"]["tracking_id"].attrs["hostname"].decode('utf8')
    except KeyError:
        app_data['app_vars']['hn'] = "NA"
    try:
        # Sequencing kit
        app_data['app_vars']['sk'] = file["UniqueGlobalKey"]["context_tags"].attrs["sequencing_kit"].decode('utf8')
    except KeyError:
        app_data['app_vars']['sk'] = "NA"
    try:
        # Flowcell type
        app_data['app_vars']['fc_t'] = file["UniqueGlobalKey"]["context_tags"].attrs["flowcell_type"].decode('utf8')
    except KeyError:
        app_data['app_vars']['fc_t'] = "NA"
    try:
        # ASIC ID
        app_data['app_vars']['asic'] = file["UniqueGlobalKey"]["tracking_id"].attrs["asic_id"].decode('utf8')
    except KeyError:
        app_data['app_vars']['asic'] = "NA"
    try:
        # Experiment start
        app_data['app_vars']['exp_d'] = parser.parse(
            file["UniqueGlobalKey"]["tracking_id"].attrs["exp_start_time"].decode('utf8')).strftime(
            '%d-%b-%Y %H:%M:%S')
    except KeyError:
        app_data['app_vars']['exp_d'] = "NA"

    return file, sf, channel_list


# noinspection PyUnboundLocalVariable
def parse_position(attr, old, new):
    if new[0] == "@":
        fq = new[1:]
        fq_list = fq.split(" ")
        for k, item in enumerate(fq_list):
            if k == 0:
                read_id = item
            if item.split("=")[0] == "ch":
                channel_num = item.split("=")[1]
                channel_str = "Channel_{num}".format(num=channel_num)
        # Get ch_str, start, end
        # If read_id and ch not set...
        # noinspection PyUnboundLocalVariable
        if read_id and channel_str:
            int_data_path = app_data['bulkfile']["IntermediateData"][channel_str]["Reads"]
            int_data_labels = {
                'read_id': int_data_path["read_id"],
                'read_start': int_data_path["read_start"],
            }
            df = pd.DataFrame(data=int_data_labels)
            df.read_start = df.read_start / app_data['app_vars']['sf']
            df.read_id = df.read_id.str.decode('utf8')
            df = df.where(df.read_id == read_id)
            df = df.dropna()
            # !!! check that multiple rows are still here
            start_time = math.floor(df.iloc[0, :].read_start)
            end_time = math.ceil(df.iloc[-1, :].read_start)
        app_data['wdg_dict']['position'].value = "{ch}:{start}-{end}".format(
            ch=channel_num,
            start=start_time,
            end=end_time
        )
    elif re.match(r'^[0-9]{1,3}:[0-9]{1,9}-[0-9]{1,9}', new):
        # https://regex101.com/r/zkN1j2/1
        coords = new.split(":")
        times = coords[1].split("-")
        channel_num = coords[0]
        channel_str = "Channel_{num}".format(num=channel_num)
        (start_time, end_time) = times[0], times[1]
    else:
        channel_str = None
        channel_num = None
        start_time = None
        end_time = None

    if int(end_time) > app_data['app_vars']['len_ds']:
        end_time = app_data['app_vars']['len_ds']
    app_data['app_vars']['channel_str'] = channel_str
    app_data['app_vars']['channel_num'] = int(channel_num)
    app_data['app_vars']['start_time'] = int(start_time)
    app_data['app_vars']['end_time'] = int(end_time)

    app_data['wdg_dict']['position'].value = "{ch}:{start}-{end}".format(
        ch=app_data['app_vars']['channel_num'],
        start=app_data['app_vars']['start_time'],
        end=app_data['app_vars']['end_time']
    )

    update()


def update_data(bulkfile, app_vars):
    app_vars['duration'] = app_vars['end_time'] - app_vars['start_time']
    # get times and squiggles
    app_vars['start_squiggle'] = math.floor(app_vars['start_time'] * app_vars['sf'])
    app_vars['end_squiggle'] = math.floor(app_vars['end_time'] * app_vars['sf'])
    # get data in numpy arrays
    step = 1 / app_vars['sf']
    app_data['x_data'] = np.arange(app_vars['start_time'], app_vars['end_time'], step)
    app_data['y_data'] = bulkfile["Raw"][app_vars['channel_str']]["Signal"][()]
    app_vars['len_ds'] = len(app_data['y_data']) / app_vars['sf']
    app_data['y_data'] = app_data['y_data'][app_vars['start_squiggle']:app_vars['end_squiggle']]
    # get annotations
    path = bulkfile["IntermediateData"][app_vars['channel_str']]["Reads"]
    fields = ['read_id', 'read_start', 'modal_classification']
    app_data['label_df'], app_data['label_dt'] = get_annotations(path, fields, 'modal_classification')
    # print("Labels:")
    # print("Original df:\t", len(app_data['label_df']))
    # d1 = len(app_data['label_df'].drop_duplicates(subset=['read_id'], keep="first"))
    # print("Drop on one:\t", d1)
    # d2 = len(app_data['label_df'].drop_duplicates(subset=['read_id', 'modal_classification'], keep="first"))
    # print("Drop on two:\t", d2)
    # print("Difference  \t", d2-d1)
    app_data['label_df'] = app_data['label_df'].drop_duplicates(subset=['read_id', 'modal_classification'], keep="first")
    app_data['label_df'].read_start = app_data['label_df'].read_start / app_vars['sf']
    app_data['label_df'].read_id = app_data['label_df'].read_id.str.decode('utf8')

    path = bulkfile["StateData"][app_vars['channel_str']]["States"]
    fields = ['acquisition_raw_index', 'summary_state']
    state_label_df, state_label_dtypes = get_annotations(path, fields, 'summary_state')
    state_label_df.acquisition_raw_index = state_label_df.acquisition_raw_index / app_vars['sf']
    state_label_df = state_label_df.rename(
        columns={'acquisition_raw_index': 'read_start', 'summary_state': 'modal_classification'}
    )
    app_data['label_df'] = app_data['label_df'].append(state_label_df, ignore_index=True)
    app_data['label_df'].sort_values(by='read_start', ascending=True, inplace=True)
    app_data['label_dt'].update(state_label_dtypes)


def get_annotations(path, fields, enum_field):
    data_labels = {}
    for field in fields:
        data_labels[field] = path[field]
    data_dtypes = {}
    if h5py.check_dtype(enum=path.dtype[enum_field]):
        dataset_dtype = h5py.check_dtype(enum=path.dtype[enum_field])
        # data_dtype may lose some dataset dtypes there are duplicates of 'v'
        data_dtypes = {v: k for k, v in dataset_dtype.items()}
    labels_df = pd.DataFrame(data=data_labels)
    return labels_df, data_dtypes


def update():
    update_data(
        app_data['bulkfile'],
        app_data['app_vars']
    )
    if app_data['INIT']:
        build_widgets()
        layout.children[0] = widgetbox(list(app_data['wdg_dict'].values()), width=int(cfg_po['wdg_width']))
        app_data['INIT'] = False
    app_data['wdg_dict']['duration'].text = "Duration: {d} seconds".format(d=app_data['app_vars']['duration'])
    app_data['wdg_dict']['toggle_smoothing'].active = True
    layout.children[1] = create_figure(
        app_data['x_data'],
        app_data['y_data'],
        app_data['wdg_dict'],
        app_data['app_vars']
    )


def update_other(attr, old, new):
    update()


def build_widgets():
    """"""
    check_labels = []
    jump_list = []
    check_active = []
    app_data['label_mp'] = {}
    for k, v in enumerate(app_data['label_dt'].items()):
        app_data['label_mp'][v[0]] = k
        check_labels.append(v[1])
        if v[1] in cfg_lo:
            if cfg_lo[v[1]] == 'True':
                check_active.append(k)
                jump_list.append((v[1], str(v[0])))
        else:
            print("label {v} is in your bulk-file but not defined in config.ini".format(v=v[1]))
            check_active.append(k)

    wdg = app_data['wdg_dict']
    wdg['duration'] = PreText(text="Duration: {d} seconds".format(d=app_data['app_vars']['duration']), css_classes=['duration_pre'])
    wdg['navigation_label'] = Div(text='Navigation:', css_classes=['navigation-dropdown', 'help-text'])
    wdg['navigation_text'] = Div(
        text="""Use the <code><b>Jump to ...</b></code> buttons to find the next or previous event type.
                """,
        css_classes=['navigation-drop']
    )
    wdg['jump_next'] = Dropdown(label="Jump to next", button_type="primary", menu=jump_list, css_classes=['jump-block'])
    wdg['jump_prev'] = Dropdown(label="Jump to previous", button_type="primary", menu=jump_list)

    wdg['export_label'] = Div(text='Export data:', css_classes=['export-dropdown', 'help-text'])
    wdg['export_text'] = Div(
        text="""Export data, as a read file, from the current squiggle shown. These are written to the output directory 
                specified in your config file.
                """,
        css_classes=['export-drop']
    )
    wdg['save_read_file'] = Button(
        label="Save read file",
        button_type="success",
        css_classes=[]
    )
    wdg['bulkfile_info'] = Div(text='Bulkfile info', css_classes=['bulkfile-dropdown', 'caret-down'])
    wdg['bulkfile_help'] = Div(text='Bulkfile help:', css_classes=['bulkfile-help-dropdown', 'help-text', 'bulkfile-drop'])
    wdg['bulkfile_help_text'] = Div(
        text="""Export data, as a read file, from the current squiggle shown. These are written to the output directory 
                specified in your config file.
                """,
        css_classes=['bulkfile-help-drop']
    )
    wdg['bulkfile_text'] = Div(
        text="""<b>Experiment:</b> <br><code>{exp}</code><br>
                <b>Flowcell ID:</b> <br><code>{fc_id}</code><br>
                <b>MinKNOW version:</b> <br><code>{mk_ver}</code><br>
                <b>MinION ID:</b> <br><code>{m_id}</code><br>
                <b>Hostname:</b> <br><code>{hn}</code><br>
                <b>Sequencing kit:</b> <br><code>{sk}</code><br>
                <b>Flowcell type:</b> <br><code>{fc_t}</code><br>
                <b>ASIC ID:</b> <br><code>{asic}</code><br>
                <b>Experiment start:</b> <br><code>{exp_d}</code>
                """.format(
        exp=app_data['app_vars']['exp'],
        fc_id=app_data['app_vars']['fc_id'],
        mk_ver=app_data['app_vars']['mk_ver'],
        m_id=app_data['app_vars']['m_id'],
        hn=app_data['app_vars']['hn'],
        sk=app_data['app_vars']['sk'],
        fc_t=app_data['app_vars']['fc_t'],
        asic=app_data['app_vars']['asic'],
        exp_d=app_data['app_vars']['exp_d']
        ),
        css_classes=['bulkfile-drop']
    )
    wdg['label_options'] = Div(text='Select annotations', css_classes=['filter-dropdown', 'caret-down'])
    wdg['filter_help'] = Div(text='filter help:', css_classes=['filter-help-dropdown', 'help-text', 'filter-drop'])
    wdg['filter_help_text'] = Div(
        text="""Export data, as a read file, from the current squiggle shown. These are written to the output directory 
                specified in your config file.
                """,
        css_classes=['filter-help-drop']
    )
    wdg['toggle_annotations'] = Toggle(
        label="Display annotations",
        button_type="danger",
        css_classes=['toggle_button_g_r', 'filter-drop'],
        active=True
    )
    wdg['label_filter'] = CheckboxGroup(labels=check_labels, active=check_active, css_classes=['filter-drop'])
    
    wdg['plot_options'] = Div(text='Plot Adjustments', css_classes=['adjust-dropdown', 'caret-down'])
    wdg['adjust_help'] = Div(text='adjust help:', css_classes=['adjust-help-dropdown', 'help-text', 'adjust-drop'])
    wdg['adjust_help_text'] = Div(
        text="""Export data, as a read file, from the current squiggle shown. These are written to the output directory 
                specified in your config file.
                """,
        css_classes=['adjust-help-drop']
    )
    wdg['po_width'] = TextInput(title='Plot Width (px)', value=cfg_po['plot_width'], css_classes=['adjust-drop'])
    wdg['po_height'] = TextInput(title='Plot Height (px)', value=cfg_po['plot_height'], css_classes=['adjust-drop'])
    wdg['label_height'] = TextInput(
        title="Annotation height (y-axis)",
        value=cfg_po['label_height'],
        css_classes=['adjust-drop']
    )
    wdg['po_y_max'] = TextInput(title="y max", value=cfg_po['y_max'], css_classes=['adjust-drop'])
    wdg['po_y_min'] = TextInput(title="y min", value=cfg_po['y_min'], css_classes=['adjust-drop'])
    wdg['toggle_y_axis'] = Toggle(
        label="Fixed Y-axis",
        button_type="danger",
        css_classes=['toggle_button_g_r', 'adjust-drop'],
        active=False
    )
    wdg['toggle_smoothing'] = Toggle(
        label="Smoothing",
        button_type="danger",
        css_classes=['toggle_button_g_r', 'adjust-drop'],
        active=True
    )

    wdg['label_filter'].on_change('active', update_other)
    wdg['jump_next'].on_click(next_update)
    wdg['jump_prev'].on_click(prev_update)
    wdg['save_read_file'].on_click(export_data)

    for name in toggle_inputs:
        wdg[name].on_click(toggle_button)
    for name in int_inputs:
        wdg[name].on_change('value', is_input_int)
    return wdg


def create_figure(x_data, y_data, wdg, app_vars):
    if wdg["toggle_smoothing"].active:
        w_range = app_vars['duration']
        divisor = math.e ** 2.5
        thin_factor = math.ceil(w_range / divisor)
    else:
        thin_factor = 1
    if thin_factor == 0:
        thin_factor = 1

    greater_delete_index = np.argwhere(y_data > int(cfg_po['upper_cut_off']))
    x_data = np.delete(x_data, greater_delete_index)
    y_data = np.delete(y_data, greater_delete_index)

    lesser_delete_index = np.argwhere(y_data < int(cfg_po['lower_cut_off']))
    x_data = np.delete(x_data, lesser_delete_index)
    y_data = np.delete(y_data, lesser_delete_index)

    data = {
        'x': x_data[::thin_factor],
        'y': y_data[::thin_factor],
    }

    source = ColumnDataSource(data=data)

    p = figure(
        plot_height=int(wdg['po_height'].value),
        plot_width=int(wdg['po_width'].value),
        toolbar_location="right",
        tools=['xpan', 'xbox_zoom', 'undo', 'reset', 'save'],
        active_drag="xpan",
    )
    if cfg_po['output_backend'] not in output_backend:
        p.output_backend = 'canvas'
    else:
        p.output_backend = cfg_po['output_backend']
    # Add step/% points plotted: Step: {sp} ({pt:.3f}) -> sp=thin_factor, pt=1/thin_factor
    p.add_layout(Title(
        text="Channel: {ch} Start: {st} End: {ed} Sample rate: {sf}".format(
            ch=app_vars['channel_num'],
            st=app_vars['start_time'],
            ed=app_vars['end_time'],
            sf=app_vars['sf']
        )),
        'above'
    )
    p.add_layout(Title(
        text="Bulk-file: {s}".format(s=app_data['wdg_dict']["file_list"].value)),
        'above'
    )

    p.toolbar.logo = None
    p.yaxis.axis_label = "Raw signal"
    p.yaxis.major_label_orientation = "horizontal"
    p.xaxis.axis_label = "Time (seconds)"
    p.line(source=source, x='x', y='y', line_width=1)
    p.xaxis.major_label_orientation = math.radians(45)
    p.x_range.range_padding = 0.01

    if wdg['toggle_y_axis'].active:
        p.y_range = Range1d(int(wdg['po_y_min'].value), int(wdg['po_y_max'].value))

    if wdg['toggle_annotations'].active:
        # Here labels are thinned out
        slim_label_df = app_data['label_df'][
            (app_data['label_df']['read_start'] >= app_vars['start_time']) &
            (app_data['label_df']['read_start'] <= app_vars['end_time'])
            ]
        for index, label in slim_label_df.iterrows():
            if label.modal_classification in app_data['label_mp']:
                if app_data['label_mp'][label.modal_classification] in wdg['label_filter'].active:
                    event_line = Span(
                        location=label.read_start,
                        dimension='height',
                        line_color='green',
                        line_dash='dashed',
                        line_width=1
                    )
                    p.add_layout(event_line)
                    labels = Label(
                        x=label.read_start,
                        y=int(wdg['label_height'].value),
                        text="{cl} - {ri}".format(cl=app_data['label_dt'][label.modal_classification], ri=label.read_id),
                        level='glyph',
                        x_offset=0,
                        y_offset=0,
                        render_mode='canvas',
                        angle=-300
                    )
                    p.add_layout(labels)
    return p


def is_input_int(attr, old, new):
    try:
        int(new)
        for wdg in int_inputs:
            if (app_data['wdg_dict'][wdg].value == new) and ('input-error' in app_data['wdg_dict'][wdg].css_classes):
                input_error(app_data['wdg_dict'][wdg], 'remove')
    except ValueError:
        for wdg in int_inputs:
            if app_data['wdg_dict'][wdg].value == new:
                input_error(app_data['wdg_dict'][wdg], 'add')
                return

    new = new.lstrip('0')
    update()


def toggle_button(state):
    layout.children[1] = create_figure(
        app_data['x_data'],
        app_data['y_data'],
        app_data['wdg_dict'],
        app_data['app_vars']
    )


def input_error(widget, mode):
    """"""
    if mode == 'add':
        widget.css_classes.append('input-error')
    elif mode == 'remove':
        if widget.css_classes:
            del widget.css_classes[-1]
    else:
        print("mode not recognised")


def next_update(value):
    if value != 'reset':
        value = int(value)
        jump_start = app_data['label_df'][
            (app_data['label_df']['read_start'] > app_data['app_vars']['start_time'] + 1) &
            (app_data['label_df']['modal_classification'] == value)
            ]
        try:
            app_data['app_vars']['start_time'] = int(math.floor(jump_start['read_start'].iloc[0]))
        except IndexError:
            app_data['wdg_dict']['duration'].text += "\n{ev} event not found".format(ev=app_data['label_dt'][value])
            return
        except Exception as e:
            print(type(e))
            print(e)
        app_data['app_vars']['end_time'] = app_data['app_vars']['start_time'] + app_data['app_vars']['duration']
        app_data['wdg_dict']['position'].value = "{ch}:{start}-{end}".format(
            ch=app_data['app_vars']['channel_num'],
            start=app_data['app_vars']['start_time'],
            end=app_data['app_vars']['end_time']
        )
        layout.children[1] = create_figure(
            app_data['x_data'],
            app_data['y_data'],
            app_data['wdg_dict'],
            app_data['app_vars']
        )
        app_data['wdg_dict']['jump_next'].value = "reset"
    else:
        return


def prev_update(value):
    if value != 'reset':
        value = int(value)
        jump_start = app_data['label_df'][
            (app_data['label_df']['read_start'] < app_data['app_vars']['start_time']) &
            (app_data['label_df']['modal_classification'] == value)
            ]
        try:
            app_data['app_vars']['start_time'] = int(math.floor(jump_start['read_start'].iloc[-1]))
        except IndexError:
            app_data['wdg_dict']['duration'].text += "\n{ev} event not found".format(ev=app_data['label_dt'][value])
            return
        except Exception as e:
            print(type(e))
            print(e)
        app_data['app_vars']['end_time'] = app_data['app_vars']['start_time'] + app_data['app_vars']['duration']
        app_data['wdg_dict']['position'].value = "{ch}:{start}-{end}".format(
            ch=app_data['app_vars']['channel_num'],
            start=app_data['app_vars']['start_time'],
            end=app_data['app_vars']['end_time']
        )
        layout.children[1] = create_figure(
            app_data['x_data'],
            app_data['y_data'],
            app_data['wdg_dict'],
            app_data['app_vars']
        )
        app_data['wdg_dict']['jump_prev'].value = "reset"
    else:
        return


def export_data():
    try:
        start_val = math.floor(app_data['app_vars']['start'] * app_data['app_vars']['sf'])
        end_val = math.ceil(app_data['app_vars']['end'] * app_data['app_vars']['sf'])
    except KeyError:
        start_val = app_data['app_vars']['start_squiggle']
        end_val = app_data['app_vars']['end_squiggle']
    if export_read_file(
        app_data['app_vars']['channel_num'],
        start_val,
        end_val,
        app_data['bulkfile'],
        cfg_dr['out']
    ) == 0:
        app_data['wdg_dict']['duration'].text += "\nread file created"
    else:
        app_data['wdg_dict']['duration'].text += "\nError: read file not created"


def range_update(attr, old, new):
    app_data['app_vars'][attr] = new


app_data = {
    'file_src': None,  # bulkfile path (string)
    'bulkfile': None,  # bulkfile object
    'x_data': None,  # numpy ndarray time points
    'y_data': None,  # numpy ndarray signal data
    'label_df': None,  # pandas df of signal labels
    'label_dt': None,  # dict of signal enumeration
    'label_mp': None,  # dict matching labels to widget filter
    'app_vars': {  # dict of variables used in plots and widgets
        'len_ds': None,  # length of signal dataset
        'start_time': None,  # squiggle start time in seconds
        'end_time': None,  # squiggle end time in seconds
        'duration': None,  # squiggle duration in seconds
        'start_squiggle': None,  # squiggle start position (samples)
        'end_squiggle': None,  # squiggle end position (samples)
        'channel_str': None,  # 'Channel_NNN' (string)
        'channel_num': None,  # Channel number (int)
        'sf': None,  # sample frequency (int)
        'channel_list': None,  # list of all channels as int
    },
    'wdg_dict': None,  # dictionary of widgets
    'controls': None,  # widgets added to widgetbox
    'pore_plt': None,  # the squiggle plot
    'INIT': True  # Initial plot with bulkfile (bool)
}

int_inputs = ['po_width', 'po_height', 'po_y_min', 'po_y_max', 'label_height']
toggle_inputs = ['toggle_y_axis', 'toggle_annotations', 'toggle_smoothing']

app_data['app_vars']['files'] = []
p = Path(cfg_dr['dir'])
app_data['app_vars']['files'] = [(x.name, x.name) for x in p.iterdir() if x.suffix == '.fast5']
for index, file in enumerate(app_data['app_vars']['files']):
    file = file[0]
    bulk_file = h5py.File(Path(Path(cfg_dr['dir']) / file), 'r')
    try_path = bulk_file["Raw"]
    for i, channel in enumerate(try_path):
        if i == 0:
            try:
                try_path[channel]["Signal"][0]
            except KeyError:
                del app_data['app_vars']['files'][index]
        break
    bulk_file.flush()
    bulk_file.close()

app_data['app_vars']['files'].insert(0, ("", "--"))

app_data['wdg_dict'] = init_wdg_dict()
app_data['controls'] = widgetbox(list(app_data['wdg_dict'].values()), width=int(cfg_po['wdg_width']))

f = figure(toolbar_location=None)
f.line(x=[0], y=[0])
f.outline_line_color = None
f.toolbar.logo = None
f.xaxis.visible = False
f.yaxis.visible = False
f.xgrid.visible = False
f.ygrid.visible = False
app_data['pore_plt'] = f

layout = row(
    app_data['controls'],
    app_data['pore_plt']
)

curdoc().add_root(layout)
curdoc().title = "bulkvis"