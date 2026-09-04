# python-excel-automation
A collection of Python scripts to automate Excel tasks, simplify complex formulas, process data, and improve productivity using Pandas and OpenPyXL.

<h4 style="font-size:16px;">🖼️ Image to WebP Conversion</h4>
<pre><code>python convert_to_webp.py</code></pre>

<h4 style="font-size:16px;">📐 Image Resize with Background Removal</h4>
<p>Resizes images onto a fixed 800x1000 canvas without stretching, automatically removes the background (e.g. a white studio backdrop) using AI, and centers the subject on a transparent canvas. Output is saved as lossless PNG with original colors and quality preserved.</p>
<h5 style="font-size:14px;">1. Install the dependencies</h5>
<pre><code>pip install pillow rembg onnxruntime</code></pre>
<h5 style="font-size:14px;">2. Run the script</h5>
<pre><code>python resize_images.py "raw images"</code></pre>
<p>Or specify a custom output folder:</p>
<pre><code>python resize_images.py "raw images" "final images"</code></pre>

<h4 style="font-size:16px;">📊 Numbers to CSV Conversion</h4>
<h5 style="font-size:14px;">1. Install the dependency</h5>
<pre><code>pip install numbers-parser</code></pre>
<h5 style="font-size:14px;">2. Run the script</h5>
<pre><code>python numbers_to_csv.py</code></pre>
<p>Or specify a folder / output location:</p>
<pre><code>python numbers_to_csv.py /path/to/folder -o /path/to/output</code></pre>

<h4 style="font-size:16px;">🎬 Video Compression</h4>
<h5 style="font-size:14px;">1. Install the dependency</h5>
<p>Requires <code>ffmpeg</code> installed and available in your system PATH.</p>
<h5 style="font-size:14px;">2. Compress a single video</h5>
<pre><code>python compress_video.py input.mp4 output.mp4 --size 15</code></pre>
<p>Or compress an entire folder of videos at once:</p>
<pre><code>python compress_video.py --folder /path/to/folder --outdir compressed --size 15</code></pre>
