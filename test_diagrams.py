print("=== Diagrams 라이브러리 테스트 ===")

try:
    print("1. 기본 import 테스트...")
    import diagrams
    print("   ✅ diagrams 패키지 import 성공")
    
    print("2. 세부 모듈 import 테스트...")
    from diagrams import Diagram, Cluster, Edge
    print("   ✅ 기본 클래스들 import 성공")
    
    from diagrams.aws.network import VPC, PrivateSubnet, PublicSubnet, InternetGateway, NATGateway
    print("   ✅ AWS 네트워크 컴포넌트들 import 성공")
    
    from diagrams.aws.compute import EC2
    from diagrams.aws.security import SecurityGroup
    from diagrams.aws.general import Internet
    print("   ✅ 추가 AWS 컴포넌트들 import 성공")
    
    print("3. 간단한 다이어그램 생성 테스트...")
    with Diagram("Test", show=False, filename="test_diagram"):
        internet = Internet("Internet")
        vpc = VPC("Test VPC")
        internet >> vpc
    
    print("   ✅ 다이어그램 생성 성공")
    print("   📁 test_diagram.png 파일이 생성되었는지 확인하세요")
    
    print("\n🎉 모든 테스트 통과! Diagrams 라이브러리가 정상 작동합니다.")
    
except ImportError as e:
    print(f"   ❌ Import 오류: {e}")
except Exception as e:
    print(f"   ❌ 실행 오류: {e}")
    print(f"   원인: Graphviz가 설치되지 않았을 가능성")
    print("   해결: sudo yum install graphviz (Amazon Linux)")
