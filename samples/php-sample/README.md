## Challenge Structure

```
php-sample/
├── challenge/
│   ├── index.php          # Main challenge file
│   └── flag.txt           # Flag file (this would be injected at runtime)
├── Dockerfile             # Docker image definition
└── metadata.json          # Challenge metadata
```

## How It Works

1. **metadata.json**: Defines challenge name, category, points, flag, and port configuration
2. **Dockerfile**: Creates the container image with PHP and Apache
3. **challenge/**: Contains the challenge files that will be copied into the container
4. **index.php**: The main challenge application that users interact with

## Building Locally

To test this challenge locally:

```bash
# 1. Build the Docker image
docker build -t xctf-web:php-sample .

# 2. Run the container
docker run -d -p 9000:8000 \
  -e CHALLENGE_NAME="PHP Sample Challenge" \
  -e FLAG_VALUE="FLAG{sample_flag_value}" \
  xctf-web:php-sample

# 3. Access the challenge
# Open http://localhost:9000 in your browser
```

## Challenge Details

This is a simple challenge that:
- Shows a welcome page with challenge instructions
- Has a flag endpoint that displays the flag when accessed correctly
- Demonstrates basic PHP web challenge structure

## Integration with X-CTF Platform

To add this challenge to your X-CTF platform:

1. Copy this directory to your `$CHALLENGES_DIR` directory
2. Run the setup command:
   ```bash
   python manage.py setup_challenges --challenge-name php-sample
   ```

The platform will:
- Build the Docker image
- Create the challenge in the database
- Make it available to users

## Notes

- The flag is passed as a build argument (`FLAG_VALUE`) during Docker build
- Port 8000 is required as the main web server port
- Additional TCP ports can be specified in `metadata.json` if needed
