"""Shared labels and a complete mission-information header for saved figures."""
import textwrap
import matplotlib.dates as mdates
from matplotlib.font_manager import FontProperties


def add_aos_los_labels(axis,start_time,end_time,y_position,graph_start=None,graph_end=None,fontsize=7):
    span=max(1,(graph_end-graph_start).total_seconds()) if graph_start is not None and graph_end is not None else None
    for prefix,when,offset in [('AOS',start_time,9),('LOS',end_time,-9)]:
        if prefix=='AOS' and graph_start is not None and when<=graph_start:continue
        if prefix=='LOS' and graph_end is not None and when>=graph_end:continue
        fraction=(when-graph_start).total_seconds()/span if span else .5
        alignment='left' if fraction<.15 else 'right' if fraction>.85 else 'center'
        dx=3 if alignment=='left' else -3 if alignment=='right' else 0
        axis.annotate(f"{prefix} {when:%H:%M:%S}",xy=(when,y_position),xytext=(dx,offset),textcoords='offset points',
                      ha=alignment,va='bottom' if offset>0 else 'top',fontsize=fontsize,color='#475569',
                      annotation_clip=True,bbox=dict(facecolor='white',edgecolor='none',alpha=.8,pad=.35),zorder=6)


def add_schedule_label(axis,start_time,end_time,y_position,label,label_position='auto',fontsize=8):
    start=mdates.date2num(start_time);end=mdates.date2num(end_time);middle=(start+end)/2
    # Fit all text lines, rather than assuming that a three-minute bar is wide.
    renderer=axis.figure.canvas.get_renderer()
    font=FontProperties(size=fontsize,weight='bold')
    text_width=max(renderer.get_text_width_height_descent(line,font,False)[0] for line in str(label).splitlines())
    bar_width=abs(axis.transData.transform((end,y_position))[0]-axis.transData.transform((start,y_position))[0])
    if label_position=='auto' and text_width+14<bar_width*.78:
        color='#102031'
        if axis.patches:
            r,g,b,_=axis.patches[-1].get_facecolor()
            if .2126*r+.7152*g+.0722*b<.47:color='white'
        axis.text(middle,y_position,label,ha='center',va='center',fontsize=fontsize,fontweight='bold',color=color,clip_on=True,zorder=7)
    else:
        low,high=axis.get_xlim();fraction=(middle-low)/max(1e-12,high-low)
        alignment='left' if fraction<.15 else 'right' if fraction>.85 else 'center'
        below=label_position=='below'
        axis.annotate(label,xy=(middle,y_position),xytext=(0,-17 if below else 17),textcoords='offset points',
                      ha=alignment,va='top' if below else 'bottom',fontsize=max(6.5,fontsize-.5),fontweight='bold',
                      color='#172b40',bbox=dict(boxstyle='round,pad=.22',facecolor='white',edgecolor='#d4dee7',alpha=.95),
                      arrowprops=dict(arrowstyle='-',color='#71869a',linewidth=.65),annotation_clip=True,zorder=8)


def add_graph_information(axis,event_name=None,event_type=None,start_time=None,end_time=None,event_time=None,
                          maximum_visible=None,ground_station_location=None,landing_site_location=None,y_position=1.015):
    # Retain every original field; draw in figure coordinates during final layout.
    rows=[]
    first=[]
    if event_name:first.append(f'Event: {event_name}')
    if event_type:first.append(f'Event Type: {event_type}')
    if ground_station_location:first.append(f'Ground Station: {ground_station_location}')
    if landing_site_location:first.append(f'Landing Site: {landing_site_location}')
    if first:rows.append('  |  '.join(first))
    if start_time is not None and end_time is not None:rows.append(f'Time Span: {start_time:%Y-%m-%d %H:%M:%S UTC} – {end_time:%Y-%m-%d %H:%M:%S UTC}')
    last=[]
    if event_time is not None:last.append(f'Event Time: {event_time:%Y-%m-%d %H:%M:%S UTC}')
    if maximum_visible is not None:last.append(f'Maximum Mutually Visible Satellites: {maximum_visible}')
    if last:rows.append('  |  '.join(last))
    axis.figure._meosar_header_lines=[line for row in rows for line in textwrap.wrap(row,width=155,break_long_words=False,break_on_hyphens=False)]
