terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state in S3 so both you and CI share the same state file.
  # Create the bucket once manually before running `terraform init`.
  backend "s3" {
    bucket = "bughunter-tfstate"
    key    = "worker/terraform.tfstate"
    region = "us-east-1"
    encrypt = true
  }
}

provider "aws" {
  region = var.aws_region
}

# ──────────────────────────────────────────────
# Data — latest Amazon Linux 2023 AMI
# ──────────────────────────────────────────────
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ──────────────────────────────────────────────
# Networking — use the default VPC for now
# ──────────────────────────────────────────────
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# ──────────────────────────────────────────────
# Security Group — SSH (from your IP) + egress only
# ──────────────────────────────────────────────
resource "aws_security_group" "worker" {
  name        = "bughunter-worker-sg"
  description = "BugHunter ARQ worker - inbound SSH only"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "bughunter-worker-sg" }
}

# ──────────────────────────────────────────────
# IAM Role — lets the EC2 instance pull SSM params
# ──────────────────────────────────────────────
resource "aws_iam_role" "worker" {
  name = "bughunter-worker-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm_readonly" {
  role       = aws_iam_role.worker.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMReadOnlyAccess"
}

resource "aws_iam_instance_profile" "worker" {
  name = "bughunter-worker-profile"
  role = aws_iam_role.worker.name
}

# ──────────────────────────────────────────────
# Key Pair — public key stored in tfvars
# ──────────────────────────────────────────────
resource "aws_key_pair" "deployer" {
  key_name   = "bughunter-deployer"
  public_key = var.ssh_public_key
}

# ──────────────────────────────────────────────
# EC2 Instance
# ──────────────────────────────────────────────
resource "aws_instance" "worker" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.deployer.key_name
  vpc_security_group_ids = [aws_security_group.worker.id]
  iam_instance_profile   = aws_iam_instance_profile.worker.name
  subnet_id              = tolist(data.aws_subnets.default.ids)[0]

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  # Bootstrap: install Python 3.11, Docker, Git, then set up the systemd service.
  user_data = templatefile("${path.module}/userdata.sh.tpl", {
    redis_url              = var.redis_url
    database_url           = var.database_url
    webhook_secret         = var.webhook_secret
    github_app_id          = var.github_app_id
    github_private_key_b64 = var.github_private_key_b64
  })

  tags = {
    Name        = "bughunter-worker"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# ──────────────────────────────────────────────
# Elastic IP — stable address for SSH + GitHub
# ──────────────────────────────────────────────
resource "aws_eip" "worker" {
  instance = aws_instance.worker.id
  domain   = "vpc"
  tags     = { Name = "bughunter-worker-eip" }
}
