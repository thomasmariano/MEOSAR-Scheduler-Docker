"""Shared presentation only; satellite colors and title metadata remain upstream."""
import re
from datetime import timezone
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator


def natural_key(value):
    return tuple((0,int(piece)) if piece.isdigit() else (1,piece.lower()) for piece in re.split(r'(\d+)',str(value)))


def polish_timeline(figure,axis,start,end,row_count,count_axis=None):
    figure.patch.set_facecolor('#ffffff')
    axis.set_facecolor('#f8fafc')
    axis.set_axisbelow(True)
    for row in range(row_count):
        if row%2==0:axis.axhspan(row-.48,row+.48,color='#eaf0f6',alpha=.65,zorder=0)
    for spine in axis.spines.values():spine.set_color('#c5d0db');spine.set_linewidth(.8)
    axis.tick_params(axis='both',colors='#334155',labelsize=9,length=3,pad=7)
    axis.xaxis.label.set_color('#334155');axis.yaxis.label.set_color('#334155')
    axis.xaxis.label.set_fontsize(10);axis.yaxis.label.set_fontsize(10)
    axis.grid(axis='x',color='#c8d4df',linestyle=(0,(3,4)),linewidth=.7,alpha=.8)
    if start is not None and end is not None:
        span=(end-start).total_seconds()
        locator=mdates.AutoDateLocator(tz=timezone.utc,minticks=4,maxticks=10,interval_multiples=True)
        axis.xaxis.set_major_locator(locator)
        format_string='%H:%M:%S' if span<600 else '%m-%d\n%H:%M' if start.date()!=end.date() or span>=86400 else '%H:%M'
        axis.xaxis.set_major_formatter(mdates.DateFormatter(format_string,tz=timezone.utc))
        axis.set_xlabel('UTC Time'+(' · date shown at ticks' if '%m-%d' in format_string else ''))
        for label in axis.get_xticklabels():label.set_rotation(0);label.set_ha('center')
    if row_count:
        axis.set_ylim(row_count-.4,-.6)
    if count_axis is not None:
        count_axis.set_facecolor('#f4f7fb')
        count_axis.yaxis.set_major_locator(MaxNLocator(nbins=5,integer=True))
        low,high=count_axis.get_ylim();count_axis.set_ylim(0,max(1,high)+.5)
        count_axis.tick_params(axis='both',colors='#334155',labelsize=9)
        count_axis.yaxis.label.set_color('#334155')
        count_axis.yaxis.label.set_fontsize(9)
        count_axis.set_ylabel(count_axis.get_ylabel().replace(' Satellites','\nSatellites'))
        count_axis.grid(axis='y',color='#d7e0e9',linewidth=.7)
        count_axis.set_xlabel(axis.get_xlabel());axis.set_xlabel('')
        axis.tick_params(axis='x',labelbottom=False)
        for spine in count_axis.spines.values():spine.set_color('#c5d0db')
        for line in count_axis.lines:
            line.set_color('#183b56');line.set_linewidth(1.8);line.set_alpha(.95)
        # Show the mission event in both panels without adding a second title block.
        for line in list(axis.lines):
            if line.get_linestyle()=='--':
                x=line.get_xdata()
                if len(x)==2:count_axis.axvline(x[0],linestyle='--',color='#087c96',linewidth=1,alpha=.7)
        handles,labels=count_axis.get_legend_handles_labels()
        if handles:count_axis.legend(handles,labels,loc='upper right',fontsize=8,framealpha=.94,facecolor='white',edgecolor='#c5d0db')
    # Fixed physical header space makes layout consistent even for very tall charts.
    title=axis.get_title();axis.set_title('')
    if title:figure.suptitle(title,x=.5,y=.985,fontsize=15,fontweight='bold',color='#122b40')
    lines=getattr(figure,'_meosar_header_lines',[])
    height=figure.get_figheight()
    for index,line in enumerate(lines):
        figure.text(.5,1-(.51+index*.18)/height,line,ha='center',va='top',fontsize=8.5,color='#334155')
    reserved=max(1.25,.68+len(lines)*.18)
    figure.subplots_adjust(left=.19 if row_count>10 else .105,right=.965,
                           bottom=.72/height,top=1-reserved/height,hspace=.12)
