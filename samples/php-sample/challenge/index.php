<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PHP Sample Challenge</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background-color: #f4f4f4;
        }
        .container {
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }
        .info {
            background-color: #e7f3ff;
            border-left: 4px solid #2196F3;
            padding: 15px;
            margin: 20px 0;
        }
        .code {
            background-color: #f4f4f4;
            padding: 10px;
            border-radius: 5px;
            font-family: monospace;
            margin: 10px 0;
        }
        .flag {
            background-color: #fff3cd;
            border: 2px solid #ffc107;
            padding: 15px;
            margin: 20px 0;
            border-radius: 5px;
            text-align: center;
            font-weight: bold;
            color: #856404;
        }
        a {
            color: #2196F3;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Sample Challenge</h1>
        
        <div class="info">
            <strong>Welcome!</strong> This is a sample challenge for the X-CTF platform.
        </div>

        <h2>Challenge Instructions</h2>
        <p>This is a demonstration challenge that shows how challenges work on the X-CTF platform.</p>
        
        <h3>Getting Started</h3>
        <ul>
            <li>This challenge runs on PHP <?php echo phpversion(); ?></li>
            <li>The web server is Apache running on port 8000</li>
            <li>Challenge files are located in <code>/var/www/html</code></li>
        </ul>

        <h3>Finding the Flag</h3>
        <p>The flag is hidden somewhere in this challenge. Can you find it?</p>
        <p>Try accessing different endpoints or files to discover the flag!</p>

        <div class="info">
            <strong>Hint:</strong> Check the URL parameters or try common file paths.
        </div>

        <?php
        if (isset($_GET['flag']) && $_GET['flag'] === 'true') {
            $flag = getenv('FLAG_VALUE');
            if (!$flag) {
                $flag = 'FLAG{sample_php_challenge_flag}';
            }
            echo '<div class="flag">';
            echo '<h3>Flag Found!</h3>';
            echo '<p>' . htmlspecialchars($flag) . '</p>';
            echo '<p><small>Note: This is a sample challenge. In a real CTF, finding the flag would be much harder!</small></p>';
            echo '</div>';
        }
        ?>

        <h3>Challenge Files</h3>
        <div class="code">
            <p><strong>Current file:</strong> <?php echo __FILE__; ?></p>
            <p><strong>Server software:</strong> <?php echo $_SERVER['SERVER_SOFTWARE'] ?? 'Unknown'; ?></p>
            <p><strong>PHP version:</strong> <?php echo phpversion(); ?></p>
        </div>

        <h3>Resources</h3>
        <ul>
            <li><a href="?flag=true">View Flag (for testing)</a></li>
            <li><a href="/">Home</a></li>
        </ul>

        <hr>
        <p><small>This is a sample challenge. In a real CTF, the flag would be more difficult to obtain!</small></p>
    </div>
</body>
</html>

