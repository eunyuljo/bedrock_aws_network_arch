#!/usr/bin/env python3
import boto3
import json
from datetime import datetime
from collections import defaultdict

class AWSArchitectureMapper:
    def __init__(self):
        self.ec2 = boto3.client('ec2', region_name='ap-northeast-2')
        self.rds = boto3.client('rds', region_name='ap-northeast-2')
        self.elbv2 = boto3.client('elbv2', region_name='ap-northeast-2')

    def collect_infrastructure_data(self):
        """실제 인프라 구성 요소 수집"""
        print("🔍 AWS 인프라 구성 요소 수집 중...")
        
        data = {}
        
        # 네트워크 기본 구조
        print("  - VPC 및 서브넷 정보...")
        data['vpcs'] = self.ec2.describe_vpcs()['Vpcs']
        data['subnets'] = self.ec2.describe_subnets()['Subnets']
        data['route_tables'] = self.ec2.describe_route_tables()['RouteTables']
        data['igws'] = self.ec2.describe_internet_gateways()['InternetGateways']
        data['nats'] = self.ec2.describe_nat_gateways()['NatGateways']
        
        # 실제 배치된 리소스들
        print("  - EC2 인스턴스...")
        data['instances'] = self.get_ec2_instances()
        
        print("  - RDS 데이터베이스...")
        data['rds_instances'] = self.get_rds_instances()
        
        print("  - 로드밸런서...")
        data['load_balancers'] = self.get_load_balancers()
        
        return data

    def get_ec2_instances(self):
        """EC2 인스턴스 상세 정보"""
        instances = []
        try:
            response = self.ec2.describe_instances()
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    if instance['State']['Name'] == 'terminated':
                        continue
                    
                    instance_info = {
                        'InstanceId': instance['InstanceId'],
                        'InstanceType': instance['InstanceType'],
                        'State': instance['State']['Name'],
                        'SubnetId': instance.get('SubnetId'),
                        'VpcId': instance.get('VpcId'),
                        'PrivateIpAddress': instance.get('PrivateIpAddress'),
                        'PublicIpAddress': instance.get('PublicIpAddress'),
                        'AvailabilityZone': instance.get('Placement', {}).get('AvailabilityZone'),
                        'SecurityGroups': [sg['GroupId'] for sg in instance.get('SecurityGroups', [])],
                        'Name': self.get_tag_value(instance.get('Tags', []), 'Name'),
                        'LaunchTime': instance.get('LaunchTime'),
                        'Platform': instance.get('Platform', 'Linux'),
                        'KeyName': instance.get('KeyName')
                    }
                    instances.append(instance_info)
        except Exception as e:
            print(f"    EC2 수집 오류: {e}")
        
        return instances

    def get_rds_instances(self):
        """RDS 인스턴스 정보"""
        rds_instances = []
        try:
            response = self.rds.describe_db_instances()
            for db in response['DBInstances']:
                if db['DBInstanceStatus'] == 'deleting':
                    continue
                
                db_info = {
                    'DBInstanceIdentifier': db['DBInstanceIdentifier'],
                    'DBInstanceClass': db['DBInstanceClass'],
                    'Engine': db['Engine'],
                    'EngineVersion': db['EngineVersion'],
                    'DBInstanceStatus': db['DBInstanceStatus'],
                    'AvailabilityZone': db.get('AvailabilityZone'),
                    'MultiAZ': db.get('MultiAZ', False),
                    'VpcId': db.get('DBSubnetGroup', {}).get('VpcId'),
                    'SubnetIds': [subnet['SubnetIdentifier'] for subnet in db.get('DBSubnetGroup', {}).get('Subnets', [])],
                    'Endpoint': db.get('Endpoint', {}).get('Address'),
                    'Port': db.get('Endpoint', {}).get('Port'),
                    'AllocatedStorage': db.get('AllocatedStorage'),
                    'DBName': db.get('DBName')
                }
                rds_instances.append(db_info)
        except Exception as e:
            print(f"    RDS 수집 오류: {e}")
        
        return rds_instances

    def get_load_balancers(self):
        """로드밸런서 정보"""
        load_balancers = []
        try:
            response = self.elbv2.describe_load_balancers()
            for lb in response['LoadBalancers']:
                lb_info = {
                    'LoadBalancerName': lb['LoadBalancerName'],
                    'LoadBalancerArn': lb['LoadBalancerArn'],
                    'Type': lb['Type'],
                    'Scheme': lb['Scheme'],
                    'State': lb['State']['Code'],
                    'VpcId': lb.get('VpcId'),
                    'SubnetIds': [az['SubnetId'] for az in lb.get('AvailabilityZones', [])],
                    'DNSName': lb.get('DNSName'),
                    'CreatedTime': lb.get('CreatedTime')
                }
                load_balancers.append(lb_info)
        except Exception as e:
            print(f"    ELB 수집 오류: {e}")
        
        return load_balancers

    def get_tag_value(self, tags, key):
        """태그에서 값 추출"""
        for tag in tags:
            if tag['Key'] == key:
                return tag['Value']
        return None

    def analyze_subnet_type(self, subnet, route_tables):
        """서브넷 타입 분석"""
        subnet_id = subnet['SubnetId']
        vpc_id = subnet['VpcId']
        
        # 연결된 라우트 테이블 찾기
        associated_rt = None
        for rt in route_tables:
            if rt['VpcId'] != vpc_id:
                continue
            for assoc in rt.get('Associations', []):
                if assoc.get('SubnetId') == subnet_id:
                    associated_rt = rt
                    break
            if associated_rt:
                break
        
        # 메인 라우트 테이블 확인
        if not associated_rt:
            for rt in route_tables:
                if rt['VpcId'] == vpc_id:
                    for assoc in rt.get('Associations', []):
                        if assoc.get('Main', False):
                            associated_rt = rt
                            break
                if associated_rt:
                    break
        
        if not associated_rt:
            return 'unknown'
        
        # 라우트 분석
        for route in associated_rt.get('Routes', []):
            if route.get('DestinationCidrBlock') == '0.0.0.0/0':
                if route.get('GatewayId', '').startswith('igw-'):
                    return 'public'
                elif route.get('NatGatewayId'):
                    return 'private'
        
        return 'isolated'

    def calculate_text_safe_name(self, text, max_length=15):
        """텍스트 길이를 안전하게 제한"""
        if not text:
            return "Unknown"
        
        if len(text) <= max_length:
            return text
        
        # 긴 텍스트를 여러 줄로 분할
        lines = []
        for i in range(0, len(text), max_length):
            lines.append(text[i:i+max_length])
        
        return '\n'.join(lines[:2])  # 최대 2줄까지만

    def analyze_complexity(self, data):
        """인프라 복잡도 분석"""
        total_resources = len(data['instances']) + len(data['rds_instances']) + len(data['load_balancers'])
        vpc_count = len(data['vpcs'])
        subnet_count = len(data['subnets'])
        
        complexity_score = vpc_count * 3 + subnet_count * 1 + total_resources * 0.5
        
        if complexity_score > 20:
            return "high", 1.8, "LR"
        elif complexity_score > 10:
            return "medium", 1.4, "TB"
        else:
            return "low", 1.0, "TB"

    def generate_architecture_diagram(self, data):
        """동적 레이아웃이 적용된 아키텍처 다이어그램 생성"""
        try:
            from diagrams import Diagram, Cluster
            from diagrams.aws.compute import EC2
            from diagrams.aws.database import RDS
            from diagrams.aws.network import ELB, InternetGateway, NATGateway
            from diagrams.onprem.network import Internet
        except ImportError:
            print("❌ diagrams 라이브러리가 설치되지 않았습니다.")
            print("   설치 명령: pip install diagrams")
            return None
        
        # 복잡도 분석
        complexity, spacing, direction = self.analyze_complexity(data)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        diagram_name = f"aws_architecture_fixed_{timestamp}"
        
        print(f"🎨 아키텍처 다이어그램 생성 중... (복잡도: {complexity}, 방향: {direction})")
        
        # 그래프 속성 설정
        graph_attr = {
            "splines": "ortho",
            "nodesep": str(0.8 * spacing),
            "ranksep": str(1.0 * spacing),
            "pad": "1.0"
        }
        
        with Diagram(
            name="AWS Infrastructure Architecture",
            filename=diagram_name,
            show=False,
            direction=direction,
            graph_attr=graph_attr
        ):
            # 인터넷
            internet = Internet("Internet")
            
            # VPC 처리
            for vpc in data['vpcs']:
                vpc_id = vpc['VpcId']
                vpc_name = self.get_tag_value(vpc.get('Tags', []), 'Name') or f"VPC-{vpc_id[-8:]}"
                
                # VPC의 리소스 수 계산
                vpc_subnets = [s for s in data['subnets'] if s['VpcId'] == vpc_id]
                total_resources = 0
                for subnet in vpc_subnets:
                    total_resources += len([i for i in data['instances'] if i.get('SubnetId') == subnet['SubnetId']])
                    total_resources += len([r for r in data['rds_instances'] if subnet['SubnetId'] in r.get('SubnetIds', [])])
                    total_resources += len([l for l in data['load_balancers'] if subnet['SubnetId'] in l.get('SubnetIds', [])])
                
                vpc_display_name = self.calculate_text_safe_name(vpc_name, 20)
                
                with Cluster(f"{vpc_display_name}\n{vpc['CidrBlock']}\n({total_resources} resources)"):
                    
                    # Internet Gateway
                    igw_node = None
                    for igw in data['igws']:
                        for attachment in igw.get('Attachments', []):
                            if attachment.get('VpcId') == vpc_id and attachment.get('State') == 'available':
                                igw_node = InternetGateway("IGW")
                                internet >> igw_node
                                break
                    
                    # 가용영역별 그룹화
                    az_groups = defaultdict(list)
                    for subnet in vpc_subnets:
                        az = subnet['AvailabilityZone']
                        az_groups[az].append(subnet)
                    
                    # 각 AZ 처리
                    for az, subnets in az_groups.items():
                        
                        # AZ별 리소스 수 계산
                        az_resources = 0
                        for subnet in subnets:
                            az_resources += len([i for i in data['instances'] if i.get('SubnetId') == subnet['SubnetId']])
                            az_resources += len([r for r in data['rds_instances'] if subnet['SubnetId'] in r.get('SubnetIds', [])])
                            az_resources += len([l for l in data['load_balancers'] if subnet['SubnetId'] in l.get('SubnetIds', [])])
                        
                        if az_resources == 0:
                            continue  # 리소스가 없는 AZ는 건너뛰기
                        
                        with Cluster(f"AZ: {az[-1]} ({az_resources} resources)"):
                            
                            # 서브넷별 리소스 배치
                            for subnet in subnets:
                                subnet_id = subnet['SubnetId']
                                subnet_name = self.get_tag_value(subnet.get('Tags', []), 'Name')
                                if not subnet_name:
                                    subnet_name = f"subnet-{subnet_id[-8:]}"
                                
                                subnet_type = self.analyze_subnet_type(subnet, data['route_tables'])
                                
                                # 서브넷의 리소스들
                                subnet_instances = [i for i in data['instances'] if i.get('SubnetId') == subnet_id]
                                subnet_rds = [r for r in data['rds_instances'] if subnet_id in r.get('SubnetIds', [])]
                                subnet_elbs = [l for l in data['load_balancers'] if subnet_id in l.get('SubnetIds', [])]
                                
                                subnet_resource_count = len(subnet_instances) + len(subnet_rds) + len(subnet_elbs)
                                
                                if subnet_resource_count == 0:
                                    continue  # 리소스가 없는 서브넷은 건너뛰기
                                
                                subnet_display_name = self.calculate_text_safe_name(subnet_name, 15)
                                
                                with Cluster(f"{subnet_display_name}\n({subnet_type})\n{subnet['CidrBlock']}"):
                                    
                                    # EC2 인스턴스
                                    for instance in subnet_instances:
                                        name = instance.get('Name') or f"EC2-{instance['InstanceId'][-8:]}"
                                        safe_name = self.calculate_text_safe_name(name, 12)
                                        
                                        node_label = f"{safe_name}\n{instance['InstanceType']}\n{instance['State']}"
                                        ec2_node = EC2(node_label)
                                        
                                        # IGW 연결 (Public 서브넷인 경우)
                                        if subnet_type == 'public' and igw_node:
                                            igw_node >> ec2_node
                                    
                                    # RDS 인스턴스
                                    for rds in subnet_rds:
                                        name = rds['DBInstanceIdentifier']
                                        safe_name = self.calculate_text_safe_name(name, 12)
                                        
                                        node_label = f"{safe_name}\n{rds['Engine']}\n{rds['DBInstanceStatus']}"
                                        rds_node = RDS(node_label)
                                    
                                    # 로드밸런서
                                    for elb in subnet_elbs:
                                        name = elb['LoadBalancerName']
                                        safe_name = self.calculate_text_safe_name(name, 12)
                                        
                                        node_label = f"{safe_name}\n{elb['Type']}\n{elb['Scheme']}"
                                        elb_node = ELB(node_label)
                                        
                                        # IGW 연결 (Public 서브넷인 경우)
                                        if subnet_type == 'public' and igw_node:
                                            igw_node >> elb_node
                            
                            # NAT Gateway 처리
                            for nat in data['nats']:
                                nat_subnet_id = nat.get('SubnetId')
                                if nat_subnet_id and nat_subnet_id in [s['SubnetId'] for s in subnets]:
                                    if nat.get('State') == 'available':
                                        nat_node = NATGateway(f"NAT-{nat['NatGatewayId'][-8:]}")
                                        if igw_node:
                                            igw_node >> nat_node
        
        print(f"✅ 아키텍처 다이어그램 생성 완료: {diagram_name}.png")
        print(f"   복잡도: {complexity}, 간격배수: {spacing:.1f}, 방향: {direction}")
        
        return f"{diagram_name}.png"

    def generate_summary_report(self, data):
        """인프라 요약 보고서 생성"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"aws_infrastructure_report_{timestamp}.txt"
        
        complexity, spacing, direction = self.analyze_complexity(data)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("AWS INFRASTRUCTURE ANALYSIS REPORT\n")
            f.write("=" * 70 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Region: ap-northeast-2 (Seoul)\n")
            f.write(f"Layout Complexity: {complexity}\n")
            f.write(f"Spacing Multiplier: {spacing:.1f}\n")
            f.write(f"Diagram Direction: {direction}\n\n")
            
            # 전체 통계
            f.write("📊 INFRASTRUCTURE OVERVIEW\n")
            f.write("-" * 30 + "\n")
            f.write(f"VPCs: {len(data['vpcs'])}\n")
            f.write(f"Subnets: {len(data['subnets'])}\n")
            f.write(f"EC2 Instances: {len(data['instances'])}\n")
            f.write(f"RDS Instances: {len(data['rds_instances'])}\n")
            f.write(f"Load Balancers: {len(data['load_balancers'])}\n")
            f.write(f"Internet Gateways: {len(data['igws'])}\n")
            f.write(f"NAT Gateways: {len(data['nats'])}\n\n")
            
            # VPC별 상세 정보
            for i, vpc in enumerate(data['vpcs'], 1):
                vpc_id = vpc['VpcId']
                vpc_name = self.get_tag_value(vpc.get('Tags', []), 'Name') or f"VPC-{i}"
                
                f.write(f"🏢 VPC #{i}: {vpc_name}\n")
                f.write("-" * 40 + "\n")
                f.write(f"VPC ID: {vpc_id}\n")
                f.write(f"CIDR Block: {vpc['CidrBlock']}\n")
                f.write(f"State: {vpc['State']}\n")
                f.write(f"Default VPC: {'Yes' if vpc.get('IsDefault', False) else 'No'}\n\n")
                
                # 이 VPC의 서브넷들
                vpc_subnets = [s for s in data['subnets'] if s['VpcId'] == vpc_id]
                f.write(f"  📍 Subnets ({len(vpc_subnets)}):\n")
                
                for subnet in vpc_subnets:
                    subnet_name = self.get_tag_value(subnet.get('Tags', []), 'Name') or subnet['SubnetId']
                    subnet_type = self.analyze_subnet_type(subnet, data['route_tables'])
                    
                    # 서브넷의 리소스 수
                    subnet_instances = [i for i in data['instances'] if i.get('SubnetId') == subnet['SubnetId']]
                    subnet_rds = [r for r in data['rds_instances'] if subnet['SubnetId'] in r.get('SubnetIds', [])]
                    subnet_elbs = [l for l in data['load_balancers'] if subnet['SubnetId'] in l.get('SubnetIds', [])]
                    
                    f.write(f"    - {subnet_name} ({subnet_type.upper()})\n")
                    f.write(f"      CIDR: {subnet['CidrBlock']}\n")
                    f.write(f"      AZ: {subnet['AvailabilityZone']}\n")
                    f.write(f"      Available IPs: {subnet.get('AvailableIpAddressCount', 'N/A')}\n")
                    f.write(f"      EC2 Instances: {len(subnet_instances)}\n")
                    f.write(f"      RDS Instances: {len(subnet_rds)}\n")
                    f.write(f"      Load Balancers: {len(subnet_elbs)}\n\n")
                
                f.write("\n")
        
        return filename

    def run(self):
        """메인 실행"""
        print("🚀 AWS Architecture Mapper (Fixed Version)")
        print("=" * 55)
        
        # 데이터 수집
        infrastructure_data = self.collect_infrastructure_data()
        
        # 통계 출력
        print(f"\n📊 인프라 현황:")
        print(f"  - VPC: {len(infrastructure_data['vpcs'])}개")
        print(f"  - 서브넷: {len(infrastructure_data['subnets'])}개")
        print(f"  - EC2 인스턴스: {len(infrastructure_data['instances'])}개")
        print(f"  - RDS 인스턴스: {len(infrastructure_data['rds_instances'])}개")
        print(f"  - 로드밸런서: {len(infrastructure_data['load_balancers'])}개")
        
        # 복잡도 분석
        complexity, spacing, direction = self.analyze_complexity(infrastructure_data)
        print(f"\n🔍 복잡도 분석:")
        print(f"  - 복잡도 레벨: {complexity}")
        print(f"  - 간격 배수: {spacing:.1f}x")
        print(f"  - 추천 방향: {direction}")
        
        # PNG 다이어그램 생성
        print(f"\n🏗️ 아키텍처 다이어그램 생성 중...")
        try:
            png_file = self.generate_architecture_diagram(infrastructure_data)
        except Exception as e:
            print(f"❌ PNG 생성 오류: {e}")
            png_file = None
        
        # 요약 보고서 생성
        print(f"\n📋 요약 보고서 생성 중...")
        report_file = self.generate_summary_report(infrastructure_data)
        
        # 결과 요약
        print(f"\n🎉 작업 완료!")
        if png_file:
            print(f"  📄 PNG 다이어그램: {png_file}")
        print(f"  📋 텍스트 보고서: {report_file}")
        
        # 서브넷별 리소스 배치 요약
        print(f"\n📋 서브넷별 리소스 배치:")
        for vpc in infrastructure_data['vpcs']:
            vpc_name = self.get_tag_value(vpc.get('Tags', []), 'Name') or vpc['VpcId']
            print(f"  🏢 {vpc_name}:")
            
            vpc_subnets = [s for s in infrastructure_data['subnets'] if s['VpcId'] == vpc['VpcId']]
            for subnet in vpc_subnets:
                subnet_name = self.get_tag_value(subnet.get('Tags', []), 'Name') or subnet['SubnetId']
                subnet_instances = [i for i in infrastructure_data['instances'] if i.get('SubnetId') == subnet['SubnetId']]
                subnet_rds = [r for r in infrastructure_data['rds_instances'] if subnet['SubnetId'] in r.get('SubnetIds', [])]
                subnet_elbs = [l for l in infrastructure_data['load_balancers'] if subnet['SubnetId'] in l.get('SubnetIds', [])]
                
                resource_count = len(subnet_instances) + len(subnet_rds) + len(subnet_elbs)
                subnet_type = self.analyze_subnet_type(subnet, infrastructure_data['route_tables'])
                
                if resource_count > 0:  # 리소스가 있는 서브넷만 표시
                    print(f"    📍 {subnet_name} ({subnet_type}): {resource_count}개 리소스")

if __name__ == "__main__":
    mapper = AWSArchitectureMapper()
    mapper.run()