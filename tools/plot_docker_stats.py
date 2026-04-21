#!/usr/bin/env python3
"""
Parse docker stats JSON file and generate plots for CPU%, Memory%, and Memory Usage over time.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import plotly.graph_objects as go
from plotly.subplots import make_subplots


def parse_memory_usage(mem_usage_str):
    """
    Parse memory usage string like "788.1MiB / 30.66GiB" and return numeric value in MiB.
    """
    try:
        used_part = mem_usage_str.split(' / ')[0].strip()
        value = float(used_part.replace('MiB', '').replace('GiB', '').replace('KiB', '').strip())
        
        if 'GiB' in used_part:
            value = value * 1024  # Convert GiB to MiB
        elif 'KiB' in used_part:
            value = value / 1024  # Convert KiB to MiB
        
        return value
    except (ValueError, IndexError):
        return None


def parse_percentage(perc_str):
    """Parse percentage string like "0.39%" to float."""
    try:
        return float(perc_str.replace('%', '').strip())
    except ValueError:
        return None


def percentile_95(values):
    """Compute the 95th percentile using linear interpolation."""
    if not values:
        return None
    if len(values) == 1:
        return values[0]

    sorted_values = sorted(values)
    rank = 0.95 * (len(sorted_values) - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = rank - lower_index
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    return lower_value + (upper_value - lower_value) * fraction


def add_series_with_average(fig, x_values, y_values, row=None, col=None, *, name, color, showlegend=False):
    """Add a metric trace and a dashed 95th-percentile reference line for the same series."""
    if not y_values:
        return

    p95_value = percentile_95(y_values)
    x_start = x_values[0]
    x_end = x_values[-1]

    series_trace = go.Scatter(
        x=x_values,
        y=y_values,
        mode='lines+markers',
        name=name,
        line=dict(color=color, width=2),
        marker=dict(size=5),
        legendgroup=name,
        showlegend=showlegend,
    )

    average_trace = go.Scatter(
        x=[x_start, x_end],
        y=[p95_value, p95_value],
        mode='lines',
        name=f"{name} p95",
        line=dict(color=color, width=2, dash='dash'),
        legendgroup=name,
        showlegend=False,
        hoverinfo='skip',
    )

    average_label_trace = go.Scatter(
        x=[x_end],
        y=[p95_value],
        mode='text',
        text=[f"p95 {p95_value:.2f}"],
        textposition='middle right',
        textfont=dict(color=color, size=10),
        name=f"{name} p95 label",
        legendgroup=name,
        showlegend=False,
        hoverinfo='skip',
    )

    if row is None or col is None:
        fig.add_trace(series_trace)
        fig.add_trace(average_trace)
        fig.add_trace(average_label_trace)
    else:
        fig.add_trace(series_trace, row=row, col=col)
        fig.add_trace(average_trace, row=row, col=col)
        fig.add_trace(average_label_trace, row=row, col=col)


def load_docker_stats(json_file):
    """Load and parse docker stats from newline-delimited JSON file."""
    data = defaultdict(lambda: {
        'timestamps': [],
        'cpu_percent': [],
        'mem_percent': [],
        'mem_usage': [],
    })
    
    try:
        with open(json_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    record = json.loads(line)
                    container_name = record.get('Name', 'unknown')
                    
                    # Parse timestamp
                    ts_str = record.get('Timestamp', '')
                    try:
                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    except ValueError:
                        print(f"Warning: Could not parse timestamp on line {line_num}: {ts_str}", file=sys.stderr)
                        continue
                    
                    # Parse metrics
                    cpu_perc = parse_percentage(record.get('CPUPerc', '0%'))
                    mem_perc = parse_percentage(record.get('MemPerc', '0%'))
                    mem_usage = parse_memory_usage(record.get('MemUsage', '0MiB'))
                    
                    # Store data
                    if cpu_perc is not None and mem_perc is not None and mem_usage is not None:
                        data[container_name]['timestamps'].append(ts)
                        data[container_name]['cpu_percent'].append(cpu_perc)
                        data[container_name]['mem_percent'].append(mem_perc)
                        data[container_name]['mem_usage'].append(mem_usage)
                    
                except json.JSONDecodeError as e:
                    print(f"Warning: Could not parse JSON on line {line_num}: {e}", file=sys.stderr)
                    continue
        
        return dict(data)
    except FileNotFoundError:
        print(f"Error: File not found: {json_file}", file=sys.stderr)
        sys.exit(1)


def create_plots(data, output_dir=None):
    """Create three interactive plots using Plotly with toggleable legend."""
    if not data:
        print("No data to plot.", file=sys.stderr)
        return
    
    # Set up output directory
    if output_dir is None:
        output_dir = Path(__file__).parent / 'data'
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create subplots with Plotly
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=("CPU Usage Over Time", "Memory Percentage Over Time", "Memory Usage Over Time"),
        vertical_spacing=0.12
    )
    
    colors = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f'
    ]
    
    # Add traces for each container
    for (container_name, metrics), color in zip(sorted(data.items()), colors):
        if metrics['timestamps']:
            add_series_with_average(
                fig,
                metrics['timestamps'],
                metrics['cpu_percent'],
                row=1,
                col=1,
                name=container_name,
                color=color,
                showlegend=True,
            )
            add_series_with_average(
                fig,
                metrics['timestamps'],
                metrics['mem_percent'],
                row=2,
                col=1,
                name=container_name,
                color=color,
            )
            add_series_with_average(
                fig,
                metrics['timestamps'],
                metrics['mem_usage'],
                row=3,
                col=1,
                name=container_name,
                color=color,
            )
    
    # Update layout
    fig.update_xaxes(title_text="Time", row=3, col=1)
    fig.update_yaxes(title_text="CPU %", row=1, col=1)
    fig.update_yaxes(title_text="Memory %", row=2, col=1)
    fig.update_yaxes(title_text="Memory Usage (MiB)", row=3, col=1)
    
    fig.update_layout(
        title_text="<b>Docker Container Metrics Over Time</b><br><sub>Click legend items to toggle containers on/off (dashed lines are p95)</sub>",
        height=1000,
        width=1400,
        hovermode='x unified',
        font=dict(size=11),
        legend=dict(groupclick='togglegroup')
    )
    
    # Save interactive HTML
    output_file = output_dir / 'docker_stats_interactive.html'
    fig.write_html(output_file)
    print(f"✓ Interactive plot saved to: {output_file}")
    print(f"  Open in a web browser and click legend items to toggle containers")
    
    # Also save individual interactive plots
    save_individual_interactive_plots(data, output_dir, colors)


def save_individual_interactive_plots(data, output_dir, colors):
    """Save individual interactive Plotly plots for each metric."""
    
    # CPU Plot
    fig_cpu = go.Figure()
    for (container_name, metrics), color in zip(sorted(data.items()), colors):
        if metrics['timestamps']:
            add_series_with_average(
                fig_cpu,
                metrics['timestamps'],
                metrics['cpu_percent'],
                name=container_name,
                color=color,
                showlegend=True,
            )
    fig_cpu.update_layout(
        title="<b>CPU Usage Over Time</b><br><sub>Click legend to toggle containers (dashed lines are p95)</sub>",
        xaxis_title="Time",
        yaxis_title="CPU %",
        hovermode='x unified',
        height=600,
        width=1200,
        legend=dict(groupclick='togglegroup')
    )
    cpu_file = output_dir / 'cpu_percent_interactive.html'
    fig_cpu.write_html(cpu_file)
    print(f"✓ Interactive CPU plot saved to: {cpu_file}")
    
    # Memory % Plot
    fig_mem_perc = go.Figure()
    for (container_name, metrics), color in zip(sorted(data.items()), colors):
        if metrics['timestamps']:
            add_series_with_average(
                fig_mem_perc,
                metrics['timestamps'],
                metrics['mem_percent'],
                name=container_name,
                color=color,
                showlegend=True,
            )
    fig_mem_perc.update_layout(
        title="<b>Memory Percentage Over Time</b><br><sub>Click legend to toggle containers (dashed lines are p95)</sub>",
        xaxis_title="Time",
        yaxis_title="Memory %",
        hovermode='x unified',
        height=600,
        width=1200,
        legend=dict(groupclick='togglegroup')
    )
    mem_perc_file = output_dir / 'memory_percent_interactive.html'
    fig_mem_perc.write_html(mem_perc_file)
    print(f"✓ Interactive memory % plot saved to: {mem_perc_file}")
    
    # Memory Usage Plot
    fig_mem_usage = go.Figure()
    for (container_name, metrics), color in zip(sorted(data.items()), colors):
        if metrics['timestamps']:
            add_series_with_average(
                fig_mem_usage,
                metrics['timestamps'],
                metrics['mem_usage'],
                name=container_name,
                color=color,
                showlegend=True,
            )
    fig_mem_usage.update_layout(
        title="<b>Memory Usage Over Time</b><br><sub>Click legend to toggle containers (dashed lines are p95)</sub>",
        xaxis_title="Time",
        yaxis_title="Memory Usage (MiB)",
        hovermode='x unified',
        height=600,
        width=1200,
        legend=dict(groupclick='togglegroup')
    )
    mem_usage_file = output_dir / 'memory_usage_interactive.html'
    fig_mem_usage.write_html(mem_usage_file)
    print(f"✓ Interactive memory usage plot saved to: {mem_usage_file}")


def main():
    if len(sys.argv) < 2:
        script_name = Path(__file__).name
        print(f"Usage: {script_name} <json_file> [output_dir]", file=sys.stderr)
        print(f"\nExample:", file=sys.stderr)
        print(f"  {script_name} tools/data/exp_1_output.json", file=sys.stderr)
        print(f"  {script_name} tools/data/exp_1_output.json tools/data/plots", file=sys.stderr)
        sys.exit(1)
    
    json_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    print(f"Loading docker stats from: {json_file}")
    data = load_docker_stats(json_file)
    
    if not data:
        print("No data loaded.", file=sys.stderr)
        sys.exit(1)
    
    print(f"Found data for {len(data)} containers:")
    for container_name, metrics in data.items():
        print(f"  - {container_name}: {len(metrics['timestamps'])} samples")
    
    print("\nGenerating plots...")
    create_plots(data, output_dir)
    print("\n✓ Done!")


if __name__ == '__main__':
    main()
