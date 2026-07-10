output "worker_public_ip" {
  description = "Elastic IP of the EC2 worker — use this in your SSH config and CI deploy step"
  value       = aws_eip.worker.public_ip
}

output "worker_instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.worker.id
}

output "worker_ami" {
  description = "AMI used for the worker instance"
  value       = data.aws_ami.al2023.id
}
