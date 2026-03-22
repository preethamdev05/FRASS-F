#!/bin/bash
set -e

echo "=========================================="
echo "  FRAS IoT System Setup"
echo "=========================================="

# Generate secrets if not set
export SECRET_KEY=${SECRET_KEY:-$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")}
export POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")}
export EDGE_API_KEY=${EDGE_API_KEY:-$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")}

echo ""
echo "Secrets generated. Save these for production:"
echo "  SECRET_KEY=$SECRET_KEY"
echo "  POSTGRES_PASSWORD=$POSTGRES_PASSWORD"
echo "  EDGE_API_KEY=$EDGE_API_KEY"
echo ""

# Create .env file
cat > .env << EOF
SECRET_KEY=$SECRET_KEY
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
EDGE_API_KEY=$EDGE_API_KEY
EOF

echo ".env file created."
echo ""
echo "To start the system:"
echo "  docker compose -f docker-compose.iot.yml up -d"
echo ""
echo "To add more edge devices, duplicate the edge-001 service"
echo "with a different FRAS_DEVICE_ID and camera device."
